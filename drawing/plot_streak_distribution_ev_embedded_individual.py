# plot_streak_ev_embedded_full.py
# All data embedded (no file I/O). Draw 4 charts:
#   1) CUT - VALID
#   2) CUT - CENSORED
#   3) CONTINUAL - VALID
#   4) CONTINUAL - CENSORED
#
# Usage:
#   python3 plot_streak_ev_embedded_full.py

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

def group_series(metric: str, scope_filter: str | None = None):
    """
    scope_filter: 'VALID' / 'CENSORED' / None(=all)
    Returns dict:
      key = "B-VALID" etc
      value = (x_list, y_list) sorted by streak_len
    """
    buckets = {}
    for r in DATA:
        if scope_filter is not None and r["scope"] != scope_filter:
            continue
        key = f"{r['side']}-{r['scope']}"
        buckets.setdefault(key, []).append(r)

    series = {}
    for key, rows in buckets.items():
        rows_sorted = sorted(rows, key=lambda x: int(x["streak_len"]))
        x = [int(rr["streak_len"]) for rr in rows_sorted]
        y = [float(rr[metric]) for rr in rows_sorted]
        series[key] = (x, y)
    return series

def plot_metric(metric: str, title: str, y_label: str, scope_filter: str | None = None):
    series = group_series(metric, scope_filter=scope_filter)

    plt.figure()
    for key, (x, y) in sorted(series.items()):
        plt.plot(x, y, marker="o", label=key)

    plt.title(title)
    plt.xlabel("Streak Length")
    plt.ylabel(y_label)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

def main():
    # ---- CUT: VALID only ----
    plot_metric(
        metric="ev_cut_pct",
        title="STREAK LEN EV (CUT) - VALID",
        y_label="EV_CUT_PCT",
        scope_filter="VALID",
    )
    plt.show()

    # ---- CUT: CENSORED only ----
    plot_metric(
        metric="ev_cut_pct",
        title="STREAK LEN EV (CUT) - CENSORED",
        y_label="EV_CUT_PCT",
        scope_filter="CENSORED",
    )
    plt.show()

    # ---- CONTINUAL: VALID only ----
    plot_metric(
        metric="ev_con_pct",
        title="STREAK LEN EV (CONTINUAL) - VALID",
        y_label="EV_CON_PCT",
        scope_filter="VALID",
    )
    plt.show()

    # ---- CONTINUAL: CENSORED only ----
    plot_metric(
        metric="ev_con_pct",
        title="STREAK LEN EV (CONTINUAL) - CENSORED",
        y_label="EV_CON_PCT",
        scope_filter="CENSORED",
    )
    plt.show()

if __name__ == "__main__":
    main()