// Fast map selection (lasso, box, click) for the settlements map.
//
// Plotly's built-in lasso/box re-styles every point of the map on each mouse move to preview
// the selection, which blocks the browser for hundreds of milliseconds per move with thousands
// of settlements (the drawn lasso loses vertices and points turn purple late). Here the outline
// is drawn on a light SVG overlay and the points inside it are computed once, on mouse-up.
// Point clicks are handled the same way (the map uses clickmode 'event', not 'event+select').
//
// The result is passed to the existing map callback through dcc.Graph's selectedData, with the
// same point fields Plotly provides (curveNumber, pointIndex, lat, lon, customdata). Shift adds
// to the current selection. Plotly's drag mode stays the source of truth for the active tool.
(function () {
    var CLICK_TOLERANCE_PX = 4;

    function getGd() {
        var el = document.getElementById('map');
        if (!el) return null;
        return el._fullLayout ? el : (el.querySelector('.js-plotly-plot') || null);
    }

    function getMap(gd) {
        var m = gd && gd._fullLayout && gd._fullLayout.map;
        return m && m._subplot && m._subplot.map;
    }

    function pointTraces(gd) {
        var out = [];
        (gd.data || []).forEach(function (t, i) {
            if (t.meta && t.meta.agcapBaseSize !== undefined && t.visible !== false && t.lat && t.lon) out.push([t, i]);
        });
        return out;
    }

    function pointObj(t, curve, i) {
        return {curveNumber: curve, pointIndex: i, pointNumber: i, lat: t.lat[i], lon: t.lon[i],
                customdata: t.customdata ? t.customdata[i] : undefined};
    }

    // Points currently selected (for Shift = add to selection)
    function currentPoints(gd) {
        var pts = [];
        pointTraces(gd).forEach(function (pair) {
            var t = pair[0];
            (t.selectedpoints || []).forEach(function (i) { pts.push(pointObj(t, pair[1], i)); });
        });
        return pts;
    }

    function emit(points, additive, clickPoint) {
        var gd = getGd();
        if (additive && gd) {
            var seen = new Set(points.map(function (p) { return p.curveNumber + ':' + p.pointIndex; }));
            currentPoints(gd).forEach(function (p) {
                if (!seen.has(p.curveNumber + ':' + p.pointIndex)) points.push(p);
            });
        }
        var props = {selectedData: {points: points}};
        if (clickPoint) props.clickData = {points: [clickPoint]};
        window.dash_clientside.set_props('map', props);
    }

    function insidePolygon(x, y, poly) {
        var inside = false;
        for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
            var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
            if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
        }
        return inside;
    }

    // Project every point once and keep those passing `test(x, y)` (container pixel coordinates)
    function collect(gd, map, test, bbox) {
        var pts = [];
        pointTraces(gd).forEach(function (pair) {
            var t = pair[0];
            for (var i = 0; i < t.lat.length; i++) {
                if (t.lat[i] == null || t.lon[i] == null) continue;
                var p = map.project([t.lon[i], t.lat[i]]);
                if (p.x < bbox[0] || p.x > bbox[2] || p.y < bbox[1] || p.y > bbox[3]) continue;
                if (test(p.x, p.y)) pts.push(pointObj(t, pair[1], i));
            }
        });
        return pts;
    }

    // Nearest point to a click, within the rendered marker radius
    function nearest(gd, map, x, y) {
        var best = null, bestD = Infinity;
        pointTraces(gd).forEach(function (pair) {
            var t = pair[0];
            var r = Math.max(6, (Number(t.marker && t.marker.size) || 4) / 2 + 3);
            for (var i = 0; i < t.lat.length; i++) {
                if (t.lat[i] == null || t.lon[i] == null) continue;
                var p = map.project([t.lon[i], t.lat[i]]);
                var d = Math.hypot(p.x - x, p.y - y);
                if (d <= r && d < bestD) { bestD = d; best = pointObj(t, pair[1], i); }
            }
        });
        return best;
    }

    function overlay(container) {
        var svg = container.querySelector(':scope > svg.agcap-select-overlay');
        if (!svg) {
            svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'agcap-select-overlay');
            svg.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:5;';
            var under = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            under.setAttribute('style', 'fill:rgba(88,60,165,0.12);stroke:#1e1e1e;stroke-width:2;');
            var dash = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            dash.setAttribute('style', 'fill:none;stroke:#fff;stroke-width:1.5;stroke-dasharray:4 3;');
            svg.appendChild(under);
            svg.appendChild(dash);
            container.appendChild(svg);
        }
        return svg;
    }

    function drawPath(svg, d) {
        svg.childNodes[0].setAttribute('d', d);
        svg.childNodes[1].setAttribute('d', d);
    }

    // --- Lasso / box: intercept left-button drags on the map while Plotly's dragmode is lasso/select ---
    document.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        var gd = getGd();
        if (!gd || !gd.contains(e.target)) return;
        if (e.target.closest && e.target.closest('.maplibregl-ctrl, .maplibregl-popup')) return;
        var mode = gd._fullLayout && gd._fullLayout.dragmode;
        if (mode !== 'lasso' && mode !== 'select') return;
        var map = getMap(gd);
        if (!map) return;

        // Stop Plotly's own selection drag (and the map) from seeing this drag
        e.preventDefault();
        e.stopPropagation();

        var container = map.getContainer();
        var rect = container.getBoundingClientRect();
        var svg = overlay(container);
        var additive = e.shiftKey;
        var x0 = e.clientX - rect.left, y0 = e.clientY - rect.top;
        var pts = [[x0, y0]];
        var last = [x0, y0];
        var moved = false;
        var frame = null;
        var follower = document.getElementById('cursor-follower');

        function render() {
            frame = null;
            if (mode === 'select') {
                var x1 = Math.min(x0, last[0]), x2 = Math.max(x0, last[0]);
                var y1 = Math.min(y0, last[1]), y2 = Math.max(y0, last[1]);
                drawPath(svg, 'M' + x1 + ',' + y1 + 'H' + x2 + 'V' + y2 + 'H' + x1 + 'Z');
            } else {
                drawPath(svg, 'M' + pts.map(function (p) { return p[0] + ',' + p[1]; }).join('L') + 'Z');
            }
        }

        function onMove(ev) {
            ev.stopPropagation();
            var x = ev.clientX - rect.left, y = ev.clientY - rect.top;
            if (follower && follower.classList.contains('active')) {
                follower.style.left = (ev.clientX + 14) + 'px';
                follower.style.top = (ev.clientY + 14) + 'px';
            }
            if (Math.hypot(x - x0, y - y0) > CLICK_TOLERANCE_PX) moved = true;
            if (Math.hypot(x - last[0], y - last[1]) < 2) return;
            last = [x, y];
            pts.push(last);
            if (!frame) frame = requestAnimationFrame(render);
        }

        function onUp(ev) {
            document.removeEventListener('mousemove', onMove, true);
            document.removeEventListener('mouseup', onUp, true);
            if (frame) cancelAnimationFrame(frame);
            drawPath(svg, '');
            if (!moved) {
                var hit = nearest(gd, map, x0, y0);
                if (hit) emit([hit], additive || ev.shiftKey, hit);
                return;
            }
            var selected;
            if (mode === 'select') {
                var bx = [Math.min(x0, last[0]), Math.min(y0, last[1]), Math.max(x0, last[0]), Math.max(y0, last[1])];
                selected = collect(gd, map, function () { return true; }, bx);
            } else {
                var xs = pts.map(function (p) { return p[0]; }), ys = pts.map(function (p) { return p[1]; });
                var bb = [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)];
                selected = collect(gd, map, function (x, y) { return insidePolygon(x, y, pts); }, bb);
            }
            emit(selected, additive || ev.shiftKey, null);
        }

        document.addEventListener('mousemove', onMove, true);
        document.addEventListener('mouseup', onUp, true);
    }, true);

    // --- Point click in pan mode: select the clicked settlement (Shift adds) ---
    function onClick(data) {
        var gd = getGd();
        if (!gd) return;
        var mode = gd._fullLayout && gd._fullLayout.dragmode;
        if (mode === 'lasso' || mode === 'select') return;  // handled by the drag interceptor
        var p = data && data.points && data.points[0];
        if (!p) return;
        var t = gd.data[p.curveNumber];
        if (!t || !t.meta || t.meta.agcapBaseSize === undefined) return;
        var i = p.pointIndex !== undefined ? p.pointIndex : p.pointNumber;
        emit([pointObj(t, p.curveNumber, i)], !!(data.event && data.event.shiftKey), null);
    }

    // (Re)bind after the graph is created or re-created by Dash (Plotly.purge drops listeners)
    function bindClick() {
        var gd = getGd();
        if (!gd || typeof gd.on !== 'function') return;
        var bound = gd._ev && gd._ev.listeners && gd._ev.listeners('plotly_click').indexOf(onClick) !== -1;
        if (!bound) gd.on('plotly_click', onClick);
    }
    setInterval(bindClick, 1000);
})();
