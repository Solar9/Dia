// Loading → data / empty / error for anything a view fetches (DIA-50).
// useResource(path) runs the request (and repeats it every `interval` ms);
// <Resource> shows the right state, so a failed api() call is never silent.
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { html } from "../html.js";
import { api } from "../api.js";
import { t } from "../i18n.js";

export function useResource(path, { interval = 0, on } = {}) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const alive = useRef(true);
  const load = useCallback(() => {
    if (!path) return Promise.resolve();
    return api(path).then(
      (data) => { if (alive.current) { setState({ data, error: "", loading: false }); on?.(data); } },
      (e) => { if (alive.current) setState((s) => ({ ...s, error: e.message || String(e), loading: false })); },
    );
  }, [path]);
  useEffect(() => {
    alive.current = true;
    setState((s) => ({ ...s, loading: true }));
    load();
    const timer = interval ? setInterval(load, interval) : 0;
    return () => { alive.current = false; clearInterval(timer); };
  }, [load, interval]);
  const setData = useCallback((data) => setState((s) => ({ ...s, data })), []);
  return { ...state, reload: load, setData };
}

const isEmpty = (data) => data == null || (Array.isArray(data) ? !data.length : false);

// quiet: optional cards say nothing while loading or when there is nothing to show,
// but an error is still shown.
export function Resource({ res, empty, emptyText, quiet = false, children }) {
  const { data, error, loading, reload } = res;
  if (error && data == null) {
    return html`<div class="state error" role="alert"><span>${t("load_failed")}: ${error}</span>
      <button class="btn ghost" onClick=${reload}>${t("retry")}</button></div>`;
  }
  if (data == null || loading && data == null) {
    return quiet ? null : html`<div class="state loading" role="status" aria-live="polite">${t("loading")}</div>`;
  }
  if ((empty ? empty(data) : isEmpty(data))) {
    return quiet ? null : html`<div class="state empty">${emptyText || t("nothing_here")}</div>`;
  }
  return html`${error ? html`<div class="state error small" role="alert"><span>${t("load_failed")}: ${error}</span>
      <button class="btn ghost" onClick=${reload}>${t("retry")}</button></div>` : null}${children(data)}`;
}

// Only the state line (loading or error) of a resource whose data the view renders itself.
export function ResourceState({ res, quiet = false }) {
  return html`<${Resource} res=${res} quiet=${quiet} empty=${() => false}>${() => null}<//>`;
}
