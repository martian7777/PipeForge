import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";

const Plot = createPlotlyComponent(Plotly);

const ACCENT = "#6c8cff";
const SEQ = "#35d0a5";

const baseLayout: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#c7cbe0", family: "Inter, system-ui, sans-serif", size: 12 },
  margin: { l: 56, r: 16, t: 36, b: 44 },
  height: 300,
  xaxis: { gridcolor: "#2b3150", zerolinecolor: "#2b3150" },
  yaxis: { gridcolor: "#2b3150", zerolinecolor: "#2b3150" },
};

function Panel({ title, data, layout }: { title: string; data: Partial<Plotly.PlotData>[]; layout?: Partial<Plotly.Layout> }) {
  return (
    <div className="card" style={{ padding: 12 }}>
      <Plot
        data={data}
        layout={{ ...baseLayout, ...layout, title: { text: title, font: { size: 14 } } }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%" }}
        useResizeHandler
      />
    </div>
  );
}

type Plots = Record<string, any>;

export default function EvalCharts({ plots }: { plots: Plots }) {
  const panels: JSX.Element[] = [];

  if (plots.confusion_matrix) {
    const { labels, z } = plots.confusion_matrix;
    panels.push(
      <Panel
        key="cm"
        title="Confusion matrix"
        data={[{ type: "heatmap", x: labels, y: labels, z, colorscale: "Blues", showscale: true } as Partial<Plotly.PlotData>]}
        layout={{ xaxis: { title: { text: "Predicted" } }, yaxis: { title: { text: "Actual" }, autorange: "reversed" } }}
      />
    );
  }

  if (plots.roc) {
    const { fpr, tpr } = plots.roc;
    panels.push(
      <Panel
        key="roc"
        title="ROC curve"
        data={[
          { type: "scatter", mode: "lines", x: fpr, y: tpr, line: { color: ACCENT, width: 2 }, name: "ROC" },
          { type: "scatter", mode: "lines", x: [0, 1], y: [0, 1], line: { color: "#555", dash: "dash" }, name: "chance" },
        ]}
        layout={{ xaxis: { title: { text: "FPR" } }, yaxis: { title: { text: "TPR" } } }}
      />
    );
  }

  if (plots.pred_vs_actual) {
    const { actual, predicted } = plots.pred_vs_actual;
    const lo = Math.min(...actual, ...predicted);
    const hi = Math.max(...actual, ...predicted);
    panels.push(
      <Panel
        key="pva"
        title="Predicted vs actual"
        data={[
          { type: "scattergl", mode: "markers", x: actual, y: predicted, marker: { color: SEQ, size: 6, opacity: 0.6 }, name: "points" },
          { type: "scatter", mode: "lines", x: [lo, hi], y: [lo, hi], line: { color: "#555", dash: "dash" }, name: "y=x" },
        ]}
        layout={{ xaxis: { title: { text: "Actual" } }, yaxis: { title: { text: "Predicted" } } }}
      />
    );
  }

  if (plots.residuals) {
    const { predicted, residual } = plots.residuals;
    panels.push(
      <Panel
        key="res"
        title="Residuals"
        data={[{ type: "scattergl", mode: "markers", x: predicted, y: residual, marker: { color: ACCENT, size: 6, opacity: 0.6 } }]}
        layout={{ xaxis: { title: { text: "Predicted" } }, yaxis: { title: { text: "Residual" } } }}
      />
    );
  }

  if (plots.feature_importance) {
    const { features, importance } = plots.feature_importance;
    // Reverse so the largest bar sits on top.
    panels.push(
      <Panel
        key="fi"
        title="Feature importance (top)"
        data={[{ type: "bar", orientation: "h", x: [...importance].reverse(), y: [...features].reverse(), marker: { color: ACCENT } }]}
        layout={{ height: Math.max(300, features.length * 22), margin: { l: 140, r: 16, t: 36, b: 44 } }}
      />
    );
  }

  if (panels.length === 0) return <p className="subtle">No evaluation plots for this model.</p>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 4 }}>
      {panels}
    </div>
  );
}
