"""Plotly theme shared by the analysis figures and the dashboard."""
import plotly.graph_objects as go
import plotly.io as pio

# Categorical slots in fixed order (colour-blind-checked ordering)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = ["#d03b3b", "#ec835a", "#f0efec", "#6da7ec", "#2a78d6"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
TEXT_PRIMARY, TEXT_SECONDARY, GRID = "#0b0b0b", "#52514e", "#e6e5e1"

template = go.layout.Template(
    layout=go.Layout(
        colorway=SERIES,
        font=dict(family="Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif", size=13, color=TEXT_PRIMARY),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=24, t=84, b=56),
        title=dict(x=0, y=0.98, yanchor="top", xanchor="left", font=dict(size=16)),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, ticks="outside", tickcolor=GRID, automargin=True,
                   title=dict(font=dict(color=TEXT_SECONDARY))),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, ticks="outside", tickcolor=GRID, automargin=True,
                   title=dict(font=dict(color=TEXT_SECONDARY))),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(color=TEXT_SECONDARY)),
        hoverlabel=dict(bgcolor="#ffffff", font=dict(color=TEXT_PRIMARY)),
        bargap=0.35,
    )
)
pio.templates["ls2"] = template
pio.templates.default = "ls2"
