//! Fantasy scoring from a raw stat line.

use std::collections::HashMap;

/// Points for one stat line under a league's scoring weights.
///
/// Mirrors `Scoring.points` in `BestBallKit` and the projection path in
/// `streamlit_app.py`: every weighted stat present is accumulated, missing
/// stats count as zero.
pub fn points(stats: &HashMap<String, f64>, scoring: &HashMap<String, f64>) -> f64 {
    let mut total = 0.0;
    for (stat, weight) in scoring {
        if let Some(value) = stats.get(stat) {
            total += value * weight;
        }
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sums_weighted_stats_and_ignores_missing_ones() {
        let stats: HashMap<String, f64> = [
            ("rec_yd", 200.0),
            ("rec", 10.0),
            ("rec_td", 1.0),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
        let scoring: HashMap<String, f64> = [
            ("rec_yd", 0.1),
            ("rec", 0.5),
            ("rec_td", 6.0),
            ("rush_yd", 0.1),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();

        assert_eq!(points(&stats, &scoring), 20.0 + 5.0 + 6.0);
    }
}
