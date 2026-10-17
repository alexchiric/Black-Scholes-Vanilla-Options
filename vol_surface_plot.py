"""Plotly figures for the output of ``data_pipeline.vol_smile_pipeline``."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font={"size": 16})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def smile_figure(smile: pd.DataFrame, title: str = "Implied volatility smile", x: str = "strike",
                 show_yahoo: bool = False) -> go.Figure:
    """One line per expiry: implied vol (%) against strike (or log-moneyness ``x='moneyness'``)."""
    if smile.empty:
        return empty_figure("No options passed the liquidity filters for this selection.")
    fig = go.Figure()
    for expiry, grp in smile.groupby("expirationDate"):
        label = f"{pd.Timestamp(expiry):%Y-%m-%d} ({grp['dte'].iloc[0]:.0f}d)"
        fig.add_trace(go.Scatter(x=grp[x], y=grp["iv"] * 100, mode="lines+markers", name=label,
                                 hovertemplate=f"{x}=%{{x:.4g}}<br>IV=%{{y:.2f}}%<extra>{label}</extra>"))
        if show_yahoo and grp["yahooIV"].notna().any():
            fig.add_trace(go.Scatter(x=grp[x], y=grp["yahooIV"] * 100, mode="markers", name=f"{label} - Yahoo IV",
                                     marker={"symbol": "circle-open", "size": 7}, opacity=0.6))
    fig.update_layout(title=title, xaxis_title="Strike" if x == "strike" else "Log-moneyness ln(K/F)",
                      yaxis_title="Implied volatility (%)", legend_title="Expiry", hovermode="closest")
    return fig


def surface_figure(smile: pd.DataFrame, title: str = "Implied volatility surface") -> go.Figure:
    """3-D surface of implied vol over (log-moneyness, days to expiry); Delaunay-triangulated."""
    if len(smile) < 4 or smile["dte"].nunique() < 2:
        return empty_figure("A surface needs at least two expiries with several liquid strikes.")
    fig = go.Figure(go.Mesh3d(x=smile["moneyness"], y=smile["dte"], z=smile["iv"] * 100, intensity=smile["iv"] * 100,
                              delaunayaxis="z", colorscale="Viridis", showscale=True,
                              colorbar={"title": "IV (%)"}, opacity=0.9))
    fig.update_layout(title=title, scene={"xaxis_title": "Log-moneyness ln(K/F)", "yaxis_title": "Days to expiry",
                                          "zaxis_title": "Implied volatility (%)"}, margin={"l": 0, "r": 0, "t": 40, "b": 0})
    return fig
