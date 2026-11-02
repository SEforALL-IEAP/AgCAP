// Sidebar filter logic shared by the clientside map and table callbacks.
// Mirrors scripts/filter_utils.py (used by CSV export, analysis charts and histograms);
// keep the two in sync:
//  - Numeric: value within [min, max]; missing values pass only if the card's
//    "Include N empty values" box is ticked (naStore[column] === true).
//  - Categorical: value among the selected options; missing values pass only if
//    the "(empty)" option (MISSING) is selected. Empty selection = no filter.
window.agcapFilters = (function () {
    var MISSING = '__missing__';

    function isMissing(v) {
        return v === null || v === undefined || v === '' || (typeof v === 'number' && isNaN(v));
    }

    // Compile filter state into index-based specs for fast per-row checks.
    function compile(colIdx, sliderIds, sliderVals, catIds, catVals, naStore) {
        var na = naStore || {};
        var sliders = [];
        (sliderIds || []).forEach(function (sid, i) {
            var range = (sliderVals || [])[i];
            var idx = colIdx[sid.column];
            if (idx === undefined || !range) return;
            sliders.push({idx: idx, lo: range[0], hi: range[1], includeMissing: na[sid.column] === true});
        });
        var cats = [];
        (catIds || []).forEach(function (cid, i) {
            var accepted = (catVals || [])[i];
            var idx = colIdx[cid.column];
            if (idx === undefined || !accepted || accepted.length === 0) return;
            cats.push({idx: idx, accepted: new Set(accepted.map(String)), includeMissing: accepted.indexOf(MISSING) > -1});
        });
        return {sliders: sliders, cats: cats};
    }

    function rowPasses(row, spec) {
        for (var i = 0; i < spec.sliders.length; i++) {
            var s = spec.sliders[i];
            var v = row[s.idx];
            if (isMissing(v)) {
                if (!s.includeMissing) return false;
            } else if (v < s.lo || v > s.hi) {
                return false;
            }
        }
        for (var j = 0; j < spec.cats.length; j++) {
            var c = spec.cats[j];
            var cv = row[c.idx];
            if (isMissing(cv)) {
                if (!c.includeMissing) return false;
            } else if (!c.accepted.has(String(cv))) {
                return false;
            }
        }
        return true;
    }

    return {MISSING: MISSING, isMissing: isMissing, compile: compile, rowPasses: rowPasses};
})();
