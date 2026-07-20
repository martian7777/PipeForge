// The pre-built distribution ships no types; reuse the @types/plotly.js definitions.
declare module "plotly.js-dist-min" {
  import * as Plotly from "plotly.js";
  export = Plotly;
}
