import { useMemo } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
// Use the pre-built distribution to keep the bundle lean.
import Plotly from "plotly.js-dist-min";
import type { ChartSpec } from "../types";

const Plot = createPlotlyComponent(Plotly);

// Coherent, accessible categorical palette (looks right on the dark panel).
const ACCENT = "#6c8cff";
const SEQ = "#35d0a5";

const baseLayout: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#c7cbe0", family: "Inter, system-ui, sans-serif", size: 12 },
  margin: { l: 48, r: 16, t: 36, b: 44 },
  height: 300,
  xaxis: { gridcolor: "#2b3150", zerolinecolor: "#2b3150" },
  yaxis: { gridcolor: "#2b3150", zerolinecolor: "#2b3150" },
};

function toTrace(spec: ChartSpec): Partial<Plotly.PlotData>[] {
  const d = spec.data as Record<string, number[] | number[][] | string[]>;
  switch (spec.kind) {
    case "histogram": {
      const bins = d.bins as number[];
      const counts = d.counts as number[];
      // Bin midpoints for a clean bar chart.
      const x = counts.map((_, i) => (bins[i] + bins[i + 1]) / 2);
      return [{ type: "bar", x, y: counts, marker: { color: ACCENT } }];
    }
    case "bar":
      return [{ type: "bar", x: d.x as string[], y: d.y as number[], marker: { color: ACCENT } }];
    case "scatter":
      return [
        {
          type: "scattergl",
          mode: "markers",
          x: d.x as number[],
          y: d.y as number[],
          marker: { color: SEQ, size: 6, opacity: 0.7 },
        },
      ];
    case "line":
      return [
        {
          type: "scatter",
          mode: "lines",
          x: d.x as string[],
          y: d.y as number[],
          line: { color: ACCENT, width: 2 },
        },
      ];
    case "heatmap":
      return [
        {
          type: "heatmap",
          x: d.labels as string[],
          y: d.labels as string[],
          z: d.z as number[][],
          colorscale: "RdBu",
          zmid: 0,
          reversescale: true,
        } as Partial<Plotly.PlotData>,
      ];
    default:
      return [];
  }
}

export default function Chart({ spec }: { spec: ChartSpec }) {
  const traces = useMemo(() => toTrace(spec), [spec]);
  const layout = useMemo<Partial<Plotly.Layout>>(
    () => ({ ...baseLayout, title: { text: spec.title, font: { size: 14 } } }),
    [spec.title]
  );
  return (
    <div className="card" style={{ padding: 12 }}>
      <Plot
        data={traces}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%" }}
        useResizeHandler
      />
    </div>
  );
}
