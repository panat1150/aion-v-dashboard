#!/usr/bin/env python3
"""AION V Intelligence Dashboard — Streamlit + Supabase"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date, datetime
from collections import defaultdict
import store

st.set_page_config(
    page_title="⚡ AION V Intelligence",
    page_icon="⚡",
    layout="wide",
)

# ── Constants ──────────────────────────────────────────────────────────────────
BAT = 75.2; PGAS = 40; PL100 = 12; CO2G = 0.50; CO2P = 2.31
BLUE   = "#58a6ff"; GREEN  = "#3fb950"; YELLOW = "#d29922"
RED    = "#f85149"; ORANGE = "#db6d28"; PURPLE = "#bc8cff"; MUTED = "#8b949e"
PBKG   = "#161b22"; GRID   = "rgba(255,255,255,0.04)"
CTYPE_CLR = {"Home": GREEN, "DC Fast": BLUE, "AC": PURPLE, "Free": ORANGE}

RATE_OPTIONS = {
    "3.02 — Home": 3.02, "2.70 — Home TOD": 2.70,
    "6.50 — DC Fast": 6.50, "7.10 — PTT ท่าแซะ": 7.10,
    "7.20 — BYD": 7.20,   "7.50 — iGreen / OC": 7.50,
    "7.90 — PTT EleX / Spark": 7.90, "8.73 — EV Anywhere": 8.73,
    "9.15 — Shell": 9.15, "0.00 — Free": 0.00,
}


# ── Data layer ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_data():
    charges = store.get_records("charge_log")
    obds    = store.get_records("obd_log")
    # recompute rolling avg
    vi = [(i, s["eff"]) for i, s in enumerate(charges) if s.get("eff", 0) > 0]
    for i, s in enumerate(charges):
        nb = [e for j, e in vi if abs(j - i) <= 2]
        s["roll"] = round(sum(nb) / len(nb), 2) if nb else None
    return charges, obds


# ── Compute ────────────────────────────────────────────────────────────────────
def compute_kpi(charges, obds):
    lat = obds[-1] if obds else {}
    ve  = [s["eff"] for s in charges if s.get("eff", 0) > 0]
    avg_eff    = round(sum(ve) / len(ve), 2) if ve else 0
    total_kwh  = round(sum(s["kwh"]  for s in charges), 1)
    total_cost = round(sum(s["cost"] for s in charges), 0)
    total_km   = (charges[-1]["odo"] - charges[0]["odo"]) if len(charges) >= 2 else 0
    pet_cpkm   = PGAS * PL100 / 100
    saved      = round(pet_cpkm * total_km - total_cost, 0)
    avg_range  = round(BAT * 0.9 / avg_eff * 100, 0) if avg_eff else 0
    co2_saved  = round(CO2P * PL100 / 100 * total_km - CO2G * total_kwh, 0)
    cpkm_avg   = round(total_cost / total_km, 2) if total_km else 0
    home_kwh   = sum(s["kwh"]  for s in charges if s.get("type") == "Home")
    home_pct   = round(home_kwh / total_kwh * 100, 1) if total_kwh else 0
    road_kwh   = total_kwh - home_kwh
    soh = lat.get("soh", 0); cyc = lat.get("cycles", 0)
    deg = round((100 - soh) / cyc, 3) if cyc > 0 else 0
    p80 = round((soh - 80) / deg + cyc, 0) if deg > 0 else 0
    kpc = round(total_km / cyc, 0) if cyc > 0 else 0
    p80km = round(p80 * kpc, 0) if p80 > 0 and kpc > 0 else 0
    best_dc = min((s["rate"] for s in charges if s.get("type") == "DC Fast" and s.get("rate", 0) > 0), default=0)
    return {
        "total_km": total_km, "sessions": len(charges),
        "total_kwh": total_kwh, "total_cost": total_cost,
        "avg_eff": avg_eff, "avg_range": avg_range,
        "saved": saved, "co2_saved": co2_saved, "cpkm": cpkm_avg,
        "pet_cpkm": pet_cpkm, "last_odo": charges[-1]["odo"] if charges else 0,
        "last_date": charges[-1]["date"] if charges else "-",
        "soh": soh, "cycles": cyc, "deg": deg, "p80": p80, "p80km": p80km,
        "spread": lat.get("spread", 0), "rt_eff": lat.get("rt_eff", 0),
        "max_temp": lat.get("max_temp", 0), "obd_date": lat.get("date", "-"),
        "obd_soc": lat.get("soc", 0), "home_pct": home_pct,
        "home_kwh": round(home_kwh, 1), "road_kwh": round(road_kwh, 1),
        "petrol_liters": round(total_km * PL100 / 100, 0),
        "trees": round(co2_saved / 21.8, 1) if co2_saved > 0 else 0,
        "best_dc": best_dc,
        "home_saving_vs_dc": round(road_kwh * (7.90 - 3.02), 0),
    }


def compute_monthly(charges):
    mk = defaultdict(float); mc = defaultdict(float)
    mhk = defaultdict(float); mdk = defaultdict(float)
    for s in charges:
        m = s.get("month") or s["date"][:7]
        mk[m] += s["kwh"]; mc[m] += s["cost"]
        if s.get("type") == "Home":      mhk[m] += s["kwh"]
        elif s.get("type") == "DC Fast": mdk[m] += s["kwh"]
    months = sorted(mk.keys())
    return {
        "labels": months,
        "kwh":  [round(mk[m], 1) for m in months],
        "cost": [round(mc[m], 0) for m in months],
        "home": [round(mhk[m], 1) for m in months],
        "dc":   [round(mdk[m], 1) for m in months],
    }


def compute_cum(charges):
    pet_cpkm = PGAS * PL100 / 100
    ev_cum = 0.0; pet_cum = 0.0; cum = []
    for s in charges:
        ev_cum  += s["cost"]
        pet_cum += pet_cpkm * s.get("dist", 0)
        cum.append({"date": s["date"], "ev": round(ev_cum), "pet": round(pet_cum)})
    return cum


def compute_stations(charges):
    sd = defaultdict(lambda: {"cnt": 0, "kwh": 0.0, "cost": 0.0, "rates": []})
    for s in charges:
        n = s.get("station") or "Unknown"
        sd[n]["cnt"] += 1; sd[n]["kwh"] += s["kwh"]; sd[n]["cost"] += s["cost"]
        if s.get("rate", 0) > 0: sd[n]["rates"].append(s["rate"])
    return sorted(
        [{"name": n, "cnt": v["cnt"], "kwh": round(v["kwh"], 1),
          "cost": round(v["cost"], 0),
          "rate": round(sum(v["rates"]) / len(v["rates"]), 2) if v["rates"] else 0}
         for n, v in sd.items()],
        key=lambda x: x["cnt"], reverse=True)[:15]


def compute_ctype(charges):
    ct = defaultdict(lambda: {"kwh": 0.0, "cost": 0.0, "cnt": 0, "eff": []})
    for s in charges:
        t = s.get("type") or "Other"
        ct[t]["kwh"] += s["kwh"]; ct[t]["cost"] += s["cost"]; ct[t]["cnt"] += 1
        if s.get("eff", 0) > 0: ct[t]["eff"].append(s["eff"])
    return {t: {"kwh": round(v["kwh"], 1), "cost": round(v["cost"], 0),
                "cnt": v["cnt"],
                "avg_eff": round(sum(v["eff"]) / len(v["eff"]), 1) if v["eff"] else 0}
            for t, v in ct.items()}


def compute_hist(charges):
    ve   = [s["eff"] for s in charges if s.get("eff", 0) > 0]
    bins = list(range(10, 40, 2))
    return [{"label": f"{bins[i]}-{bins[i+1]}",
             "cnt": sum(1 for e in ve if bins[i] <= e < bins[i+1])}
            for i in range(len(bins) - 1)]


# ── Chart helpers ──────────────────────────────────────────────────────────────
def _cfg(fig, height=None):
    fig.update_layout(
        paper_bgcolor=PBKG, plot_bgcolor=PBKG,
        font=dict(color=MUTED, size=10),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
        **({"height": height} if height else {}),
    )
    fig.update_xaxes(gridcolor=GRID, tickfont=dict(size=9))
    fig.update_yaxes(gridcolor=GRID, tickfont=dict(size=9))
    return fig


def chart_soh_gauge(soh):
    clr = GREEN if soh >= 90 else YELLOW if soh >= 80 else RED
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=soh,
        number={"suffix": "%", "font": {"size": 32, "color": clr}},
        gauge={
            "axis": {"range": [70, 100], "tickcolor": MUTED, "tickfont": {"size": 9}},
            "bar": {"color": clr, "thickness": 0.25},
            "bgcolor": PBKG, "bordercolor": "#30363d",
            "steps": [
                {"range": [70, 80], "color": "rgba(248,81,73,0.15)"},
                {"range": [80, 90], "color": "rgba(210,153,34,0.15)"},
                {"range": [90, 100], "color": "rgba(63,185,80,0.15)"},
            ],
            "threshold": {"line": {"color": RED, "width": 2}, "thickness": 0.75, "value": 80},
        },
    ))
    fig.update_layout(paper_bgcolor=PBKG, font={"color": MUTED},
                      height=200, margin=dict(l=20, r=20, t=30, b=10))
    return fig


def chart_savings(cum):
    dates = [c["date"] for c in cum]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=[c["ev"]  for c in cum],
                             name="ต้นทุน EV สะสม (฿)", fill="tozeroy",
                             line=dict(color=BLUE, width=2),
                             fillcolor="rgba(88,166,255,0.12)"))
    fig.add_trace(go.Scatter(x=dates, y=[c["pet"] for c in cum],
                             name="ถ้าใช้น้ำมัน (฿)", fill="tozeroy",
                             line=dict(color=RED, width=1.5, dash="dash"),
                             fillcolor="rgba(248,81,73,0.08)"))
    _cfg(fig, height=260)
    fig.update_yaxes(tickformat=",.0f")
    return fig


def chart_eff(charges, avg_eff):
    colors = [
        "rgba(139,148,158,0.3)" if not s.get("eff") else
        "rgba(248,81,73,0.75)"  if s["eff"] > 25 else
        "rgba(63,185,80,0.75)"  if s["eff"] < 17 else
        "rgba(88,166,255,0.7)"
        for s in charges
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[s["date"] for s in charges],
                         y=[s.get("eff") or None for s in charges],
                         marker_color=colors, name="kWh/100km",
                         marker_line_width=0))
    fig.add_trace(go.Scatter(x=[s["date"] for s in charges],
                             y=[s.get("roll") for s in charges],
                             name="Rolling 5-sess avg",
                             line=dict(color=YELLOW, dash="dash", width=2),
                             mode="lines"))
    fig.add_hline(y=avg_eff, line=dict(color="rgba(63,185,80,0.4)", dash="dot", width=1.5),
                  annotation_text=f"avg {avg_eff}",
                  annotation_font=dict(size=9, color=GREEN))
    _cfg(fig, height=240)
    fig.update_yaxes(title_text="kWh/100km", title_font=dict(size=9))
    return fig


def chart_monthly_kwh(mo):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=mo["labels"], y=mo["home"],
                         name="Home", marker_color="rgba(63,185,80,0.75)"))
    fig.add_trace(go.Bar(x=mo["labels"], y=mo["dc"],
                         name="DC Fast", marker_color="rgba(88,166,255,0.7)"))
    fig.update_layout(barmode="stack")
    _cfg(fig, height=200)
    return fig


def chart_monthly_cost(mo, charges):
    mcp = defaultdict(list)
    for s in charges:
        m = s.get("month") or s["date"][:7]
        if s.get("cpkm"): mcp[m].append(s["cpkm"])
    cpkm = [round(sum(mcp[m]) / len(mcp[m]), 2) if mcp.get(m) else None for m in mo["labels"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=mo["labels"], y=mo["cost"], name="Cost (฿)",
                         marker_color="rgba(210,153,34,0.7)", yaxis="y"))
    fig.add_trace(go.Scatter(x=mo["labels"], y=cpkm, name="฿/km (avg)",
                             line=dict(color=BLUE, width=2),
                             mode="lines+markers", marker=dict(size=5), yaxis="y2"))
    fig.update_layout(
        yaxis=dict(title="฿", title_font=dict(size=9), gridcolor=GRID),
        yaxis2=dict(title="฿/km", title_font=dict(size=9), overlaying="y",
                    side="right", showgrid=False, rangemode="tozero"),
    )
    _cfg(fig, height=200)
    return fig


def chart_stations(stations):
    s_sorted = sorted([s for s in stations if s["rate"] > 0], key=lambda x: x["rate"])
    names  = [s["name"][:18] + "…" if len(s["name"]) > 18 else s["name"] for s in s_sorted]
    rates  = [s["rate"] for s in s_sorted]
    colors = [GREEN if r < 4 else "#1a9e5c" if r < 6.5 else BLUE if r < 7.5
              else YELLOW if r < 8.5 else RED for r in rates]
    fig = go.Figure(go.Bar(
        x=rates, y=names, orientation="h",
        marker_color=colors,
        customdata=[[s["cnt"], s["kwh"], s["cost"]] for s in s_sorted],
        hovertemplate="%{y}: ฿%{x}/kWh<br>%{customdata[0]} sessions | %{customdata[1]} kWh | ฿%{customdata[2]:,.0f}<extra></extra>",
    ))
    fig.update_layout(xaxis=dict(range=[0, 10], tickprefix="฿"))
    _cfg(fig, height=280)
    return fig


def chart_type_donut(ct):
    keys = list(ct.keys())
    fig = go.Figure(go.Pie(
        labels=[f"{k} ({ct[k]['cnt']})" for k in keys],
        values=[ct[k]["kwh"] for k in keys],
        marker_colors=[CTYPE_CLR.get(k, MUTED) for k in keys],
        hole=0.4,
        hovertemplate="%{label}: %{value} kWh<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=PBKG, font={"color": MUTED},
        legend=dict(orientation="h", font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
        height=200, margin=dict(l=10, r=10, t=20, b=10),
    )
    return fig


def chart_soh_trend(obds):
    if not obds:
        return None
    fig = go.Figure(go.Scatter(
        x=[o["date"] for o in obds], y=[o["soh"] for o in obds],
        mode="lines+markers",
        line=dict(color=GREEN, width=2), fill="tozeroy",
        fillcolor="rgba(63,185,80,0.1)", marker=dict(size=6, color=GREEN),
    ))
    fig.add_hline(y=80, line=dict(color="rgba(248,81,73,0.5)", dash="dot", width=1),
                  annotation_text="80%", annotation_font=dict(size=9, color=RED))
    _cfg(fig, height=180)
    fig.update_yaxes(range=[70, 100])
    return fig


def chart_hist(hist_data, avg_eff):
    labels = [h["label"] for h in hist_data]
    cnts   = [h["cnt"]   for h in hist_data]
    colors = [
        "rgba(63,185,80,0.75)" if int(h["label"].split("-")[0]) + 1 < 17 else
        "rgba(248,81,73,0.75)" if int(h["label"].split("-")[0]) + 1 > 25 else
        "rgba(88,166,255,0.7)"
        for h in hist_data
    ]
    fig = go.Figure(go.Bar(x=labels, y=cnts, marker_color=colors, showlegend=False))
    avg_bin = f"{int((avg_eff // 2) * 2)}-{int((avg_eff // 2) * 2 + 2)}"
    if avg_bin in labels:
        fig.add_vline(x=labels.index(avg_bin) - 0.5,
                      line=dict(color="rgba(210,153,34,0.6)", width=2),
                      annotation_text="avg", annotation_font=dict(size=9, color=YELLOW))
    _cfg(fig, height=180)
    return fig


# ── Pages ──────────────────────────────────────────────────────────────────────
def page_dashboard():
    charges, obds = get_data()
    if not charges:
        st.warning("ยังไม่มีข้อมูล — รัน migrate.py ก่อน หรือเพิ่ม charge session")
        return

    k        = compute_kpi(charges, obds)
    mo       = compute_monthly(charges)
    cum      = compute_cum(charges)
    stations = compute_stations(charges)
    ct       = compute_ctype(charges)
    hist_d   = compute_hist(charges)

    st.caption(
        f"6ขธ 8343  |  Odo {k['last_odo']:,} km  |  Last charge: {k['last_date']}  |  "
        f"SoH: {k['soh']}%  |  Sessions: {k['sessions']}"
    )

    # Hero
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 ประหยัดเทียบน้ำมัน",  f"฿{k['saved']:,.0f}",
              f"{k['petrol_liters']:.0f} ลิตรที่ไม่ได้เผาไหม้")
    c2.metric("🌿 CO₂ ลดได้ (kg)",       f"{k['co2_saved']:,.0f}",
              f"≈ {k['trees']} ต้นไม้/ปี")
    c3.metric("🛣 กม. ที่ขับแล้ว",       f"{k['total_km']:,}",
              f"พิสัยเฉลี่ย: {k['avg_range']:.0f} กม.")

    st.divider()

    # Battery + Charging KPIs
    col_bat, col_kpi = st.columns(2)

    with col_bat:
        lbl = f"  <small style='color:#484f58'>snapshot: {k['obd_date']}</small>" if k["obd_date"] != "-" else ""
        st.markdown(f"**🔋 Battery Health**{lbl}", unsafe_allow_html=True)
        if k["soh"]:
            st.plotly_chart(chart_soh_gauge(k["soh"]), use_container_width=True)
        b1, b2 = st.columns(2)
        b1.metric("Cell Spread",    f"{k['spread']:.1f} mV" if k["spread"] else "—",
                  "< 5 mV = ดีมาก")
        b1.metric("Round-trip eff.", f"{k['rt_eff']*100:.1f}%" if k["rt_eff"] else "—")
        b2.metric("Max Mod Temp",   f"{k['max_temp']}°C" if k["max_temp"] else "—")
        b2.metric("SoC at OBD",     f"{k['obd_soc']}%" if k["obd_soc"] else "—")
        cyc_pct = min(k["cycles"] / 1000, 1.0) if k["cycles"] > 0 else 0.0
        st.progress(cyc_pct, text=f"Equiv. Cycles: {k['cycles']:.1f} / 1,000")
        if k["p80"] > 0 and k["p80km"] > 0:
            st.info(
                f"🔋 SoH 80% คาดที่ cycle **{k['p80']:,.0f}** "
                f"(ขับเพิ่มได้อีก ~**{k['p80km']:,.0f} km**) | "
                f"Degrade: {k['deg']:.3f}%/cycle"
            )
        else:
            st.caption("ต้องการ OBD snapshot เพิ่มเพื่อคำนวณ projection")

    with col_kpi:
        st.markdown("**⚡ Charging Overview**")
        r1 = st.columns(4)
        r1[0].metric("Sessions",        f"{k['sessions']}")
        r1[1].metric("Total kWh",       f"{k['total_kwh']:.1f}")
        r1[2].metric("ต้นทุนรวม",        f"฿{k['total_cost']:,.0f}")
        r1[3].metric("Avg Efficiency",   f"{k['avg_eff']} kWh/100")
        r2 = st.columns(4)
        r2[0].metric("Est. Full Range",  f"{k['avg_range']:.0f} km", "10% reserve")
        r2[1].metric("Cost per km",      f"฿{k['cpkm']}/km",
                     f"vs ฿{k['pet_cpkm']:.2f} น้ำมัน")
        r2[2].metric("Home Charged",     f"{k['home_pct']}%",
                     f"{k['home_kwh']:.1f} kWh")
        r2[3].metric("Best DC Rate",     f"฿{k['best_dc']}" if k["best_dc"] else "—")

    # Insights
    ins = []
    if k["home_pct"] > 50:
        ins.append(f"🏠 ชาร์จบ้าน **{k['home_pct']}%** — ประหยัด **฿{k['home_saving_vs_dc']:,.0f}** เทียบ DC")
    if k["saved"] > 0:
        ins.append(f"⛽ ถ้าใช้น้ำมัน จ่ายเพิ่ม **฿{k['saved']:,.0f}** ({k['petrol_liters']:.0f} L)")
    if k["co2_saved"] > 0:
        ins.append(f"🌿 ลด CO₂ **{k['co2_saved']:,.0f} kg** = **{k['trees']}** ต้นไม้/ปี")
    if k["p80"] > 0:
        ins.append(f"🔋 SoH 80% ที่ cycle ~**{k['p80']:,.0f}** ≈ odo **{k['last_odo'] + (k['p80km'] or 0):,} km**")
    if ins:
        cols = st.columns(len(ins))
        for col, txt in zip(cols, ins):
            col.info(txt)

    # Charts
    st.markdown("**💰 Savings Race — ต้นทุนสะสม EV vs น้ำมัน**")
    st.plotly_chart(chart_savings(cum), use_container_width=True)

    st.markdown("**⚡ Efficiency per Session (kWh/100km) — แดง=แย่ เขียว=ดี**")
    st.plotly_chart(chart_eff(charges, k["avg_eff"]), use_container_width=True)

    mc1, mc2 = st.columns(2)
    with mc1:
        st.markdown("**📅 Monthly kWh — Home 🟢 vs DC Fast 🔵**")
        st.plotly_chart(chart_monthly_kwh(mo), use_container_width=True)
    with mc2:
        st.markdown("**📅 Monthly Cost (฿) + ฿/km**")
        st.plotly_chart(chart_monthly_cost(mo, charges), use_container_width=True)

    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("**🏪 Station Leaderboard — avg ฿/kWh**")
        st.plotly_chart(chart_stations(stations), use_container_width=True)
    with sc2:
        st.markdown("**🔄 Charge Type Distribution**")
        st.plotly_chart(chart_type_donut(ct), use_container_width=True)
        for t, v in ct.items():
            clr = CTYPE_CLR.get(t, MUTED)
            st.markdown(
                f"<span style='color:{clr}'>**{t}**: {v['kwh']} kWh | "
                f"avg {v['avg_eff']} kWh/100km</span>",
                unsafe_allow_html=True,
            )

    bh1, bh2 = st.columns(2)
    with bh1:
        st.markdown("**🔋 SoH Trend — from OBD snapshots**")
        soh_fig = chart_soh_trend(obds)
        if soh_fig:
            st.plotly_chart(soh_fig, use_container_width=True)
        else:
            st.caption("ยังไม่มี OBD snapshot")
    with bh2:
        st.markdown("**📊 Efficiency Distribution**")
        st.plotly_chart(chart_hist(hist_d, k["avg_eff"]), use_container_width=True)

    # Recent sessions table
    st.markdown("**📋 Recent Charge Sessions (ล่าสุด 25)**")
    last25 = list(reversed(charges))[:25]
    df = pd.DataFrame(last25)[
        ["date", "odo", "dist", "kwh", "rate", "cost", "eff", "cpkm", "station", "type"]
    ]
    df.columns = ["Date", "Odo (km)", "Dist", "kWh", "Rate ฿", "Cost ฿",
                  "kWh/100km", "฿/km", "Station", "Type"]
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_add_charge():
    st.markdown("### ⚡ Add Charge Session")
    charges, _ = get_data()
    last_odo = charges[-1]["odo"] if charges else 0

    with st.form("charge_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d   = c1.date_input("Date", value=date.today())
        odo = c2.number_input("Odometer (km)", min_value=0, value=last_odo + 1, step=1)

        c3, c4 = st.columns(2)
        kwh         = c3.number_input("kWh Charged", min_value=0.0, step=0.001, format="%.3f")
        rate_label  = c4.selectbox("Rate (฿/kWh)", list(RATE_OPTIONS.keys()))
        rate        = RATE_OPTIONS[rate_label]
        if kwh > 0:
            c4.caption(f"Cost preview: ฿{kwh * rate:.2f}")

        c5, c6  = st.columns(2)
        station = c5.text_input("Station", value="Home")
        ctype   = c6.selectbox("Type", ["Home", "DC Fast", "AC", "Free", "Other"])
        notes   = st.text_input("Notes (optional)")

        submitted = st.form_submit_button("💾 Save Session", type="primary")

    if submitted:
        if not kwh or not odo:
            st.error("กรอก Odo และ kWh ก่อน")
            return
        all_charges = store.get_records("charge_log")
        prev_odo = max((s["odo"] for s in all_charges if s["odo"] < odo), default=None)
        dist = (odo - prev_odo) if prev_odo else 0
        cost = round(kwh * rate, 3)
        eff  = round(kwh / dist * 100, 3) if dist > 0 else 0
        cpkm = round(cost / dist, 3)       if dist > 0 else 0
        ds   = d.strftime("%Y-%m-%d")
        all_charges.append({
            "date": ds, "odo": odo, "dist": dist, "kwh": kwh, "rate": rate,
            "cost": cost, "eff": eff, "cpkm": cpkm, "station": station,
            "type": ctype, "notes": notes, "month": ds[:7],
        })
        all_charges.sort(key=lambda x: (x["date"], x["odo"]))
        store.save_records("charge_log", all_charges)
        get_data.clear()
        st.success(f"Saved: {ds} | odo {odo} | {kwh} kWh | dist {dist} km")
        st.balloons()


def _parse_obd_csv(content: bytes, filename: str) -> dict:
    import io
    df = pd.read_csv(io.BytesIO(content), sep=";", quotechar='"',
                     header=0, engine="python", on_bad_lines="skip",
                     usecols=range(6))
    df.columns = ["SECONDS", "PID", "VALUE", "UNITS", "LAT", "LON"]
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    def last_nonzero(pid):
        vals = df[df["PID"] == pid]["VALUE"].dropna()
        nz   = vals[vals != 0]
        if not nz.empty:  return float(nz.iloc[-1])
        if not vals.empty: return float(vals.iloc[-1])
        return 0.0

    # Cell voltages for min (max available as own PID)
    cell_vals = df[df["PID"].str.startswith("[BMS] Cell Voltage", na=False)]["VALUE"].dropna()
    min_cv = float(cell_vals.min()) if not cell_vals.empty else 0.0
    max_cv = last_nonzero("[BMS] Max Cell Voltage") or (float(cell_vals.max()) if not cell_vals.empty else 0.0)

    # Date from filename: "2026-05-17 07-37-28.csv" → "2026-05-17"
    try:    date_str = filename[:10]
    except: date_str = date.today().strftime("%Y-%m-%d")

    return {
        "date":     date_str,
        "session":  filename,
        "soc":      last_nonzero("[BMS] Battery Pack Display SoC"),
        "soh":      last_nonzero("[BMS] SoH"),
        "pack_v":   last_nonzero("[BMS] Battery Voltage"),
        "current":  last_nonzero("[BMS] Battery Current"),
        "max_cell_v": round(max_cv, 3),
        "min_cell_v": round(min_cv, 3),
        "max_temp": last_nonzero("[BMS] Max Module Temperature"),
        "min_temp": last_nonzero("[BMS] Min Module Temperature"),
        "tc":       last_nonzero("[BMS] Total Charged Energy"),
        "td":       last_nonzero("[BMS] Total Discharged Energy"),
        "odo":      int(last_nonzero("[BMS] Odometer")),
    }


def _save_obd_record(rec: dict, notes: str = ""):
    spread = round((rec["max_cell_v"] - rec["min_cell_v"]) * 1000, 2)
    cycles = round(rec["td"] / BAT, 1) if rec["td"] > 0 else 0
    rt_eff = round(rec["td"] / rec["tc"], 4) if rec["tc"] > 0 else 0
    all_obds = store.get_records("obd_log")
    all_obds.append({
        **rec,
        "spread": spread, "cycles": cycles, "rt_eff": rt_eff, "notes": notes,
    })
    all_obds.sort(key=lambda x: x["date"])
    store.save_records("obd_log", all_obds)
    get_data.clear()


def page_add_obd():
    st.markdown("### 🔋 Add OBD / BMS Snapshot")
    tab_csv, tab_manual = st.tabs(["📁 Upload CSV", "⌨️ Manual Entry"])

    # ── Tab 1: CSV upload ──────────────────────────────────────────────────────
    with tab_csv:
        st.caption("Upload CSV จาก OBD app (CarScanner / Torque) — semicolon-separated format")
        uploaded = st.file_uploader("เลือกไฟล์ .csv", type=["csv"], key="obd_csv")

        # Parse only when a new file is uploaded
        if uploaded:
            if st.session_state.get("_obd_csv_name") != uploaded.name:
                try:
                    st.session_state["_obd_csv_parsed"] = _parse_obd_csv(uploaded.read(), uploaded.name)
                    st.session_state["_obd_csv_name"]   = uploaded.name
                except Exception as e:
                    st.error(f"Parse error: {e}")
                    st.session_state.pop("_obd_csv_parsed", None)

        p = st.session_state.get("_obd_csv_parsed")
        if p:
            st.success(f"Parse สำเร็จ — {st.session_state['_obd_csv_name']}  |  แก้ค่าได้ก่อนกด Save")
            # Editable form pre-filled from parsed values
            # Form key includes date so it resets when new file loaded
            with st.form(f"obd_csv_form_{p['date']}"):
                c1, c2, c3 = st.columns(3)
                d_val  = datetime.strptime(p["date"], "%Y-%m-%d").date()
                d      = c1.date_input("Date",        value=d_val)
                sname  = c2.text_input("Session Name", value=p.get("session", ""))
                odo    = c3.number_input("Odometer (km) ⚠️ กรอกเอง",
                                         value=int(p["odo"]), min_value=0, step=1)
                c4, c5 = st.columns(2)
                soc = c4.number_input("SoC (%)",  0.0, 100.0,
                                      value=float(p["soc"]), step=0.1, format="%.1f")
                soh = c5.number_input("SoH (%)",  0.0, 100.0,
                                      value=float(p["soh"]), step=0.1, format="%.1f")
                c6, c7 = st.columns(2)
                pack_v  = c6.number_input("Pack V",    value=float(p["pack_v"]),  step=0.1,  format="%.1f")
                current = c7.number_input("Current A", value=float(p["current"]), step=0.01, format="%.2f")
                c8, c9, c10 = st.columns(3)
                max_cv  = c8.number_input("Max Cell V", value=float(p["max_cell_v"]), step=0.001, format="%.3f")
                min_cv  = c9.number_input("Min Cell V", value=float(p["min_cell_v"]), step=0.001, format="%.3f")
                spread  = round((max_cv - min_cv) * 1000, 2) if max_cv and min_cv else 0
                c10.metric("Cell Spread", f"{spread:.2f} mV")
                c11, c12 = st.columns(2)
                max_t = c11.number_input("Max Mod T°C", value=float(p["max_temp"]), step=0.1, format="%.1f")
                min_t = c12.number_input("Min Mod T°C", value=float(p["min_temp"]), step=0.1, format="%.1f")
                c13, c14 = st.columns(2)
                tc = c13.number_input("Total Charged kWh",    value=float(p["tc"]), step=0.1, format="%.1f")
                td = c14.number_input("Total Discharged kWh", value=float(p["td"]), step=0.1, format="%.1f")
                notes     = st.text_input("Notes (optional)")
                submitted = st.form_submit_button("💾 Save Snapshot", type="primary")

            if submitted:
                _save_obd_record({
                    "date": d.strftime("%Y-%m-%d"), "session": sname,
                    "soc": soc, "soh": soh, "odo": odo,
                    "pack_v": pack_v, "current": current,
                    "max_cell_v": max_cv, "min_cell_v": min_cv,
                    "max_temp": max_t, "min_temp": min_t, "tc": tc, "td": td,
                }, notes)
                st.session_state.pop("_obd_csv_parsed", None)
                st.session_state.pop("_obd_csv_name", None)
                st.success(f"Saved: {d.strftime('%Y-%m-%d')} SoH={soh}%")
                st.balloons()

    # ── Tab 2: Manual entry ────────────────────────────────────────────────────
    with tab_manual:
        with st.form("obd_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            d            = c1.date_input("Date", value=date.today())
            session_name = c2.text_input("Session Name")
            odo          = c3.number_input("Odometer", min_value=0, step=1)
            c4, c5 = st.columns(2)
            soc = c4.number_input("SoC (%)", 0.0, 100.0, step=0.1, format="%.1f")
            soh = c5.number_input("SoH (%)", 0.0, 100.0, step=0.1, format="%.1f")
            c6, c7 = st.columns(2)
            pack_v  = c6.number_input("Pack V",    0.0, step=0.1,  format="%.1f")
            current = c7.number_input("Current A", 0.0, step=0.01, format="%.2f")
            c8, c9, c10 = st.columns(3)
            max_cell_v = c8.number_input("Max Cell V", 0.0, step=0.001, format="%.3f")
            min_cell_v = c9.number_input("Min Cell V", 0.0, step=0.001, format="%.3f")
            spread_mv  = round((max_cell_v - min_cell_v) * 1000, 2) if max_cell_v and min_cell_v else 0
            c10.metric("Cell Spread", f"{spread_mv:.2f} mV" if spread_mv else "—")
            c11, c12, c13 = st.columns(3)
            max_mod_temp = c11.number_input("Max Mod T°C", 0.0, step=0.1, format="%.1f")
            min_mod_temp = c12.number_input("Min Mod T°C", 0.0, step=0.1, format="%.1f")
            _            = c13.number_input("Ctrl T°C",    0.0, step=0.1, format="%.1f")
            c14, c15 = st.columns(2)
            total_charged    = c14.number_input("Total Charged kWh",    0.0, step=0.1, format="%.1f")
            total_discharged = c15.number_input("Total Discharged kWh", 0.0, step=0.1, format="%.1f")
            notes     = st.text_input("Notes (optional)")
            submitted = st.form_submit_button("💾 Save OBD", type="primary")

        if submitted:
            if not soh:
                st.error("SoH จำเป็น")
                return
            ds = d.strftime("%Y-%m-%d")
            _save_obd_record({
                "date": ds, "session": session_name, "soc": soc, "soh": soh, "odo": odo,
                "pack_v": pack_v, "current": current,
                "max_cell_v": max_cell_v, "min_cell_v": min_cell_v,
                "max_temp": max_mod_temp, "min_temp": min_mod_temp,
                "tc": total_charged, "td": total_discharged,
            }, notes)
            st.success(f"OBD saved: {ds} SoH={soh}%")
            st.balloons()


# ── Edit pages ────────────────────────────────────────────────────────────────
def page_edit_charge():
    st.markdown("### ✏️ Edit / Delete Charge Session")
    charges, _ = get_data()
    if not charges:
        st.warning("ยังไม่มีข้อมูล")
        return

    indexed = list(reversed(list(enumerate(charges))))
    labels  = [f"#{i+1} | {s['date']} | odo {s['odo']:,} | {s.get('station','')} | {s['kwh']} kWh"
               for i, s in indexed]
    sel     = st.selectbox("เลือก session", labels)
    pos     = labels.index(sel)
    orig_idx, s = indexed[pos]

    rate_labels  = list(RATE_OPTIONS.keys())
    rate_default = min(rate_labels, key=lambda l: abs(RATE_OPTIONS[l] - s.get("rate", 0)))
    type_opts    = ["Home", "DC Fast", "AC", "Free", "Other"]

    with st.form(f"edit_charge_{orig_idx}"):
        c1, c2 = st.columns(2)
        d   = c1.date_input("Date",          value=datetime.strptime(s["date"], "%Y-%m-%d").date())
        odo = c2.number_input("Odometer (km)", value=int(s["odo"]), step=1)
        c3, c4 = st.columns(2)
        kwh        = c3.number_input("kWh", value=float(s["kwh"]), step=0.001, format="%.3f")
        rate_label = c4.selectbox("Rate (฿/kWh)", rate_labels,
                                  index=rate_labels.index(rate_default))
        rate = RATE_OPTIONS[rate_label]
        if kwh > 0:
            c4.caption(f"Cost: ฿{kwh * rate:.2f}")
        c5, c6  = st.columns(2)
        station = c5.text_input("Station", value=s.get("station", ""))
        ctype   = c6.selectbox("Type", type_opts,
                               index=type_opts.index(s.get("type", "Home"))
                               if s.get("type") in type_opts else 0)
        notes = st.text_input("Notes", value=s.get("notes", ""))
        cs, cd  = st.columns([4, 1])
        do_save = cs.form_submit_button("💾 Save Changes", type="primary")
        do_del  = cd.form_submit_button("🗑 Delete")

    if do_save:
        ds        = d.strftime("%Y-%m-%d")
        all_ch    = store.get_records("charge_log")
        other_odo = [c["odo"] for i, c in enumerate(all_ch) if i != orig_idx]
        prev_odo  = max((o for o in other_odo if o < odo), default=None)
        dist = (odo - prev_odo) if prev_odo else s.get("dist", 0)
        cost = round(kwh * rate, 3)
        eff  = round(kwh / dist * 100, 3) if dist > 0 else 0
        cpkm = round(cost / dist, 3)       if dist > 0 else 0
        all_ch[orig_idx] = {**all_ch[orig_idx],
                            "date": ds, "odo": odo, "dist": dist, "kwh": kwh,
                            "rate": rate, "cost": cost, "eff": eff, "cpkm": cpkm,
                            "station": station, "type": ctype, "notes": notes, "month": ds[:7]}
        all_ch.sort(key=lambda x: (x["date"], x["odo"]))
        store.save_records("charge_log", all_ch)
        get_data.clear()
        st.success("Updated")
        st.rerun()

    if do_del:
        all_ch = store.get_records("charge_log")
        all_ch.pop(orig_idx)
        store.save_records("charge_log", all_ch)
        get_data.clear()
        st.success("Deleted")
        st.rerun()


def page_edit_obd():
    st.markdown("### ✏️ Edit / Delete OBD Snapshot")
    _, obds = get_data()
    if not obds:
        st.warning("ยังไม่มี OBD snapshot")
        return

    indexed = list(reversed(list(enumerate(obds))))
    labels  = [f"#{i+1} | {o['date']} | SoH {o['soh']}% | odo {o.get('odo',0):,}"
               for i, o in indexed]
    sel     = st.selectbox("เลือก snapshot", labels)
    pos     = labels.index(sel)
    orig_idx, o = indexed[pos]

    with st.form(f"edit_obd_{orig_idx}"):
        c1, c2, c3 = st.columns(3)
        d            = c1.date_input("Date",         value=datetime.strptime(o["date"], "%Y-%m-%d").date())
        session_name = c2.text_input("Session Name", value=o.get("session", ""))
        odo          = c3.number_input("Odometer",   value=int(o.get("odo", 0)), step=1)
        c4, c5 = st.columns(2)
        soc = c4.number_input("SoC (%)", 0.0, 100.0, value=float(o.get("soc", 0)), step=0.1, format="%.1f")
        soh = c5.number_input("SoH (%)", 0.0, 100.0, value=float(o.get("soh", 0)), step=0.1, format="%.1f")
        c6, c7 = st.columns(2)
        pack_v  = c6.number_input("Pack V",    value=float(o.get("pack_v",  0)), step=0.1,  format="%.1f")
        current = c7.number_input("Current A", value=float(o.get("current", 0)), step=0.01, format="%.2f")
        c8, c9, c10 = st.columns(3)
        max_cv = c8.number_input("Max Cell V", value=float(o.get("max_cell_v", 0)), step=0.001, format="%.3f")
        min_cv = c9.number_input("Min Cell V", value=float(o.get("min_cell_v", 0)), step=0.001, format="%.3f")
        spread = round((max_cv - min_cv) * 1000, 2) if max_cv and min_cv else 0
        c10.metric("Cell Spread", f"{spread:.2f} mV" if spread else "—")
        c11, c12, c13 = st.columns(3)
        max_t = c11.number_input("Max Mod T°C", value=float(o.get("max_temp", 0)), step=0.1, format="%.1f")
        min_t = c12.number_input("Min Mod T°C", value=float(o.get("min_temp", 0)), step=0.1, format="%.1f")
        ctrl  = c13.number_input("Ctrl T°C",    value=float(o.get("tc", 0) and 0), step=0.1, format="%.1f")
        c14, c15 = st.columns(2)
        tc = c14.number_input("Total Charged kWh",    value=float(o.get("tc", 0)), step=0.1, format="%.1f")
        td = c15.number_input("Total Discharged kWh", value=float(o.get("td", 0)), step=0.1, format="%.1f")
        notes    = st.text_input("Notes", value=o.get("notes", ""))
        cs, cd   = st.columns([4, 1])
        do_save  = cs.form_submit_button("💾 Save Changes", type="primary")
        do_del   = cd.form_submit_button("🗑 Delete")

    if do_save:
        ds      = d.strftime("%Y-%m-%d")
        cycles  = round(td / BAT, 1) if td > 0 else 0
        rt_eff  = round(td / tc, 4)  if tc > 0 else 0
        all_ob  = store.get_records("obd_log")
        all_ob[orig_idx] = {**all_ob[orig_idx],
                            "date": ds, "session": session_name, "soc": soc, "soh": soh,
                            "odo": odo, "pack_v": pack_v, "current": current,
                            "max_cell_v": max_cv, "min_cell_v": min_cv, "spread": spread,
                            "max_temp": max_t, "min_temp": min_t,
                            "tc": tc, "td": td, "cycles": cycles, "rt_eff": rt_eff, "notes": notes}
        all_ob.sort(key=lambda x: x["date"])
        store.save_records("obd_log", all_ob)
        get_data.clear()
        st.success("Updated")
        st.rerun()

    if do_del:
        all_ob = store.get_records("obd_log")
        all_ob.pop(orig_idx)
        store.save_records("obd_log", all_ob)
        get_data.clear()
        st.success("Deleted")
        st.rerun()


# ── Auth ───────────────────────────────────────────────────────────────────────
def check_password():
    if st.session_state.get("authenticated"):
        return True
    with st.form("login"):
        st.markdown("### ⚡ AION V Intelligence")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            expected = st.secrets.get("password") or st.secrets["supabase"].get("password", "")
            if pw == expected:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Wrong password")
    st.stop()

check_password()

# ── Main ───────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ AION V")
    st.caption("GAC AION V Intelligence Dashboard")
    if st.button("↻ Refresh Data", use_container_width=True):
        get_data.clear()
        st.rerun()
    page = st.radio(
        "nav", ["📊 Dashboard", "⚡ Add Charge", "🔋 Add OBD",
                "✏️ Edit Charge", "✏️ Edit OBD"],
        label_visibility="collapsed",
    )

if page == "📊 Dashboard":
    page_dashboard()
elif page == "⚡ Add Charge":
    page_add_charge()
elif page == "🔋 Add OBD":
    page_add_obd()
elif page == "✏️ Edit Charge":
    page_edit_charge()
elif page == "✏️ Edit OBD":
    page_edit_obd()
