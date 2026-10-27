/* Runs the three saved cardiovascular models in the browser, for hosts without the FastAPI backend (GitHub Pages).
   The parameters come from static-api/models.json, written by src/static_api.py from the fitted sklearn pipelines.
   Each step mirrors the Python pipeline: engineered feature -> median/mode imputation -> scaling -> one-hot ->
   model. predict() returns the same shape as POST /api/predict. tests/test_static_api.py checks that the
   probabilities match sklearn's predict_proba. Works in browsers (window.ModelRuntime) and in Node (require). */
(function (root) {
  "use strict";

  const sigmoid = (z) => 1 / (1 + Math.exp(-z));
  const missing = (v) => v === null || v === undefined || v === "" || Number.isNaN(Number(v));
  const round4 = (x) => Math.round(x * 1e4) / 1e4;

  // FunctionTransformer(add_features) + ColumnTransformer(num, bin, nom), in the model's input order.
  function transform(prep, patient) {
    const row = {};
    for (const [k, v] of Object.entries(patient)) row[k] = missing(v) ? NaN : Number(v);
    row.hr_reserve_pct = (row.maxheartrate / (220 - row.age)) * 100;

    const x = [];
    prep.numeric.columns.forEach((c, i) => {
      const v = Number.isNaN(row[c]) ? prep.numeric.median[i] : row[c];
      x.push((v - prep.numeric.mean[i]) / prep.numeric.scale[i]);
    });
    prep.binary.columns.forEach((c, i) => x.push(Number.isNaN(row[c]) ? prep.binary.mode[i] : row[c]));
    prep.nominal.columns.forEach((c, i) => {
      const v = Number.isNaN(row[c]) ? prep.nominal.mode[i] : row[c];
      // handle_unknown="ignore": an unseen category is all zeros
      prep.nominal.categories[i].forEach((cat) => x.push(v === cat ? 1 : 0));
    });
    if (x.length !== prep.feature_names.length) throw new Error("feature width mismatch");
    return x;
  }

  function logistic(m, x) {
    let z = m.intercept;
    for (let i = 0; i < x.length; i++) z += m.coef[i] * x[i];
    return sigmoid(z);
  }

  function mlp(m, x) {
    let a = x;
    m.layers.forEach((layer, li) => {
      const last = li === m.layers.length - 1;
      const out = layer.bias.slice();
      for (let i = 0; i < a.length; i++) {
        const w = layer.weights[i];
        for (let j = 0; j < out.length; j++) out[j] += a[i] * w[j];
      }
      a = last ? out.map(sigmoid) : out.map((v) => (v > 0 ? v : 0)); // relu hidden, logistic output
    });
    return a[0];
  }

  function forest(m, x) {
    // sklearn trees compare float32 inputs against float64 thresholds; Math.fround matches that cast.
    const xf = x.map(Math.fround);
    let sum = 0;
    for (const t of m.trees) {
      let n = 0;
      while (t.left[n] !== -1) n = xf[t.feature[n]] <= t.threshold[n] ? t.left[n] : t.right[n];
      sum += t.p1[n];
    }
    return sum / m.trees.length;
  }

  const RUN = { logistic, mlp, forest };

  // Raw probabilities of the heart-disease class, keyed by model.
  function probabilities(bundle, patient) {
    const out = {};
    for (const key of bundle.model_order) {
      const spec = bundle.models[key];
      out[key] = RUN[spec.model.type](spec.model, transform(spec.prep, patient));
    }
    return out;
  }

  // Same response shape and rounding as backend/store.py predict().
  function predict(bundle, patient) {
    const probs = probabilities(bundle, patient);
    const thr = bundle.threshold;
    const predictions = bundle.model_order.map((key) => {
      // As in the backend: the class uses the unrounded probability; only the displayed value is rounded.
      const s = bundle.models[key], raw = probs[key], pos = raw >= thr;
      return { model: s.short, label: s.label, probability: round4(raw), predicted_class: pos ? 1 : 0,
        predicted_label: pos ? "Heart disease indicated" : "No heart disease indicated",
        test_roc_auc: s.test_roc_auc, test_accuracy: s.test_accuracy };
    });
    const ps = predictions.map((p) => p.probability);
    return { predictions, models_predicting_disease: predictions.reduce((a, p) => a + p.predicted_class, 0),
      mean_probability: round4(ps.reduce((a, b) => a + b, 0) / ps.length),
      probability_spread: round4(Math.max(...ps) - Math.min(...ps)), threshold: thr,
      imputed_fields: bundle.predictors.filter((c) => missing(patient[c])), disclaimer: bundle.disclaimer };
  }

  const api = { transform, probabilities, predict };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ModelRuntime = api;
})(typeof window !== "undefined" ? window : globalThis);
