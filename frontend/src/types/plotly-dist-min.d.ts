// Minimal ambient types for plotly.js-dist-min (pre-built UMD bundle).
// We use `any` here because we access Plotly dynamically at runtime anyway.
declare module "plotly.js-dist-min" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Plotly: any;
  export default Plotly;
}
