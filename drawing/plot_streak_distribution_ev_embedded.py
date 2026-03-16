# plot_streak_ev_3figs.py
# All data embedded (no file I/O).
#
# Produce 3 figures:
#   1) CUT + CONTINUAL - VALID
#   2) CUT + CONTINUAL - CENSORED
#   3) CUT + CONTINUAL - VALID + CENSORED
#
# Each figure draws 4 lines:
#   B-CUT, B-CONTINUAL, P-CUT, P-CONTINUAL
#
# Usage:
#   python3 plot_streak_ev_3figs.py

import matplotlib.pyplot as plt

DATA = [
    {'ev_con_pct': -2.5122, 'ev_cut_pct': 0.0125095, 'scope': 'VALID', 'side': 'B', 'streak_len': 1},
    {'ev_con_pct': -2.53067, 'ev_cut_pct': 0.0314604, 'scope': 'VALID', 'side': 'B', 'streak_len': 2},
    {'ev_con_pct': -2.54941, 'ev_cut_pct': 0.0506792, 'scope': 'VALID', 'side': 'B', 'streak_len': 3},
    {'ev_con_pct': -2.5727, 'ev_cut_pct': 0.0745679, 'scope': 'VALID', 'side': 'B', 'streak_len': 4},
    {'ev_con_pct': -2.59389, 'ev_cut_pct': 0.0962952, 'scope': 'VALID', 'side': 'B', 'streak_len': 5},
    {'ev_con_pct': -2.61215, 'ev_cut_pct': 0.115028, 'scope': 'VALID', 'side': 'B', 'streak_len': 6},
    {'ev_con_pct': -2.63702, 'ev_cut_pct': 0.140531, 'scope': 'VALID', 'side': 'B', 'streak_len': 7},
    {'ev_con_pct': -2.64665, 'ev_cut_pct': 0.150409, 'scope': 'VALID', 'side': 'B', 'streak_len': 8},
    {'ev_con_pct': -2.67782, 'ev_cut_pct': 0.18238, 'scope': 'VALID', 'side': 'B', 'streak_len': 9},
    {'ev_con_pct': -2.69473, 'ev_cut_pct': 0.199728, 'scope': 'VALID', 'side': 'B', 'streak_len': 10},
    {'ev_con_pct': -2.741, 'ev_cut_pct': 0.247182, 'scope': 'VALID', 'side': 'B', 'streak_len': 11},
    {'ev_con_pct': -2.77782, 'ev_cut_pct': 0.284944, 'scope': 'VALID', 'side': 'B', 'streak_len': 12},
    {'ev_con_pct': -2.81259, 'ev_cut_pct': 0.32061, 'scope': 'VALID', 'side': 'B', 'streak_len': 13},
    {'ev_con_pct': -2.6336, 'ev_cut_pct': 0.137025, 'scope': 'VALID', 'side': 'B', 'streak_len': 14},
    {'ev_con_pct': -2.69237, 'ev_cut_pct': 0.197298, 'scope': 'VALID', 'side': 'B', 'streak_len': 15},
    {'ev_con_pct': -2.75122, 'ev_cut_pct': 0.257663, 'scope': 'VALID', 'side': 'B', 'streak_len': 16},

    {'ev_con_pct': -2.71955, 'ev_cut_pct': 0.151561, 'scope': 'VALID', 'side': 'P', 'streak_len': 1},
    {'ev_con_pct': -2.73746, 'ev_cut_pct': 0.169026, 'scope': 'VALID', 'side': 'P', 'streak_len': 2},
    {'ev_con_pct': -2.75834, 'ev_cut_pct': 0.189381, 'scope': 'VALID', 'side': 'P', 'streak_len': 3},
    {'ev_con_pct': -2.77253, 'ev_cut_pct': 0.203214, 'scope': 'VALID', 'side': 'P', 'streak_len': 4},
    {'ev_con_pct': -2.79206, 'ev_cut_pct': 0.222262, 'scope': 'VALID', 'side': 'P', 'streak_len': 5},
    {'ev_con_pct': -2.82481, 'ev_cut_pct': 0.254194, 'scope': 'VALID', 'side': 'P', 'streak_len': 6},
    {'ev_con_pct': -2.86505, 'ev_cut_pct': 0.293426, 'scope': 'VALID', 'side': 'P', 'streak_len': 7},
    {'ev_con_pct': -2.87858, 'ev_cut_pct': 0.306614, 'scope': 'VALID', 'side': 'P', 'streak_len': 8},
    {'ev_con_pct': -2.86518, 'ev_cut_pct': 0.293553, 'scope': 'VALID', 'side': 'P', 'streak_len': 9},
    {'ev_con_pct': -2.89958, 'ev_cut_pct': 0.327088, 'scope': 'VALID', 'side': 'P', 'streak_len': 10},
    {'ev_con_pct': -2.94745, 'ev_cut_pct': 0.373765, 'scope': 'VALID', 'side': 'P', 'streak_len': 11},
    {'ev_con_pct': -2.9802, 'ev_cut_pct': 0.405696, 'scope': 'VALID', 'side': 'P', 'streak_len': 12},
    {'ev_con_pct': -3.00633, 'ev_cut_pct': 0.431167, 'scope': 'VALID', 'side': 'P', 'streak_len': 13},
    {'ev_con_pct': -3.17928, 'ev_cut_pct': 0.599797, 'scope': 'VALID', 'side': 'P', 'streak_len': 14},
    {'ev_con_pct': -2.87909, 'ev_cut_pct': 0.307115, 'scope': 'VALID', 'side': 'P', 'streak_len': 15},
    {'ev_con_pct': -2.94627, 'ev_cut_pct': 0.372618, 'scope': 'VALID', 'side': 'P', 'streak_len': 16},

    {'ev_con_pct': -1.16633, 'ev_cut_pct': -1.36786, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 1},
    {'ev_con_pct': -1.16281, 'ev_cut_pct': -1.37148, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 2},
    {'ev_con_pct': -1.17095, 'ev_cut_pct': -1.36313, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 3},
    {'ev_con_pct': -1.17661, 'ev_cut_pct': -1.35732, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 4},
    {'ev_con_pct': -1.15077, 'ev_cut_pct': -1.38383, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 5},
    {'ev_con_pct': -1.16406, 'ev_cut_pct': -1.3702, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 6},
    {'ev_con_pct': -1.14355, 'ev_cut_pct': -1.39123, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 7},
    {'ev_con_pct': -1.11265, 'ev_cut_pct': -1.42293, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 8},
    {'ev_con_pct': -1.27345, 'ev_cut_pct': -1.258, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 9},
    {'ev_con_pct': -1.0414, 'ev_cut_pct': -1.496, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 10},
    {'ev_con_pct': -1.1543, 'ev_cut_pct': -1.3802, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 11},
    {'ev_con_pct': -1.18216, 'ev_cut_pct': -1.35162, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 12},
    {'ev_con_pct': -1.36235, 'ev_cut_pct': -1.16682, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 13},
    {'ev_con_pct': -0.847413, 'ev_cut_pct': -1.69496, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 14},
    {'ev_con_pct': -1.51505, 'ev_cut_pct': -1.01021, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 15},
    {'ev_con_pct': -1.49645, 'ev_cut_pct': -1.02929, 'scope': 'CENSORED', 'side': 'B', 'streak_len': 16},

    {'ev_con_pct': -1.36334, 'ev_cut_pct': -1.17074, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 1},
    {'ev_con_pct': -1.36425, 'ev_cut_pct': -1.16985, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 2},
    {'ev_con_pct': -1.36369, 'ev_cut_pct': -1.17041, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 3},
    {'ev_con_pct': -1.34229, 'ev_cut_pct': -1.19127, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 4},
    {'ev_con_pct': -1.36516, 'ev_cut_pct': -1.16897, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 5},
    {'ev_con_pct': -1.34895, 'ev_cut_pct': -1.18477, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 6},
    {'ev_con_pct': -1.42209, 'ev_cut_pct': -1.11346, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 7},
    {'ev_con_pct': -1.33158, 'ev_cut_pct': -1.20171, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 8},
    {'ev_con_pct': -1.36436, 'ev_cut_pct': -1.16975, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 9},
    {'ev_con_pct': -1.32765, 'ev_cut_pct': -1.20554, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 10},
    {'ev_con_pct': -1.29458, 'ev_cut_pct': -1.23779, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 11},
    {'ev_con_pct': -1.55639, 'ev_cut_pct': -0.982516, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 12},
    {'ev_con_pct': -1.0553, 'ev_cut_pct': -1.47108, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 13},
    {'ev_con_pct': -1.52196, 'ev_cut_pct': -1.01609, 'scope': 'CENSORED', 'side': 'P', 'streak_len': 14},
]


def _filter_rows(scope_filter: str | None):
    if scope_filter is None:
        return DATA
    return [r for r in DATA if r["scope"] == scope_filter]


def _series_for_scope(scope_filter: str | None):
    """
    Returns dict: key -> (x, y)
      key in:
        "B-CUT", "B-CONTINUAL", "P-CUT", "P-CONTINUAL"
    """
    rows = _filter_rows(scope_filter)

    # Build per side arrays
    out = {}
    for side in ("B", "P"):
        rows_side = [r for r in rows if r["side"] == side]
        rows_side = sorted(rows_side, key=lambda x: int(x["streak_len"]))

        x = [int(r["streak_len"]) for r in rows_side]
        y_cut = [float(r["ev_cut_pct"]) for r in rows_side]
        y_con = [float(r["ev_con_pct"]) for r in rows_side]

        out[f"{side}-CUT"] = (x, y_cut)
        out[f"{side}-CONTINUAL"] = (x, y_con)

    return out


def plot_scope(scope_filter: str | None, title_prefix: str):
    series = _series_for_scope(scope_filter)

    plt.figure()
    for key, (x, y) in sorted(series.items()):
        plt.plot(x, y, marker="o", label=key)

    plt.title(title_prefix)
    plt.xlabel("Streak Length")
    plt.ylabel("EV (%)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()


def main():
    # 1) CUT + CONTINUAL - VALID
    plot_scope(scope_filter="VALID", title_prefix="STREAK LEN EV - VALID (CUT + CONTINUAL)")

    # 2) CUT + CONTINUAL - CENSORED
    plot_scope(scope_filter="CENSORED", title_prefix="STREAK LEN EV - CENSORED (CUT + CONTINUAL)")

    # 3) CUT + CONTINUAL - VALID + CENSORED
    plot_scope(scope_filter=None, title_prefix="STREAK LEN EV - ALL (VALID + CENSORED, CUT + CONTINUAL)")

    plt.show()


if __name__ == "__main__":
    main()