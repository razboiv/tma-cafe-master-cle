// Set base URL depending on your environment.
// Don't forget to add it to allowed origins on backend.
const baseUrl = 'https://web-production-razboiv.up.railway.app';

// Аккуратная склейка URL (без двойных слэшей /api//info и без пустого /api/)
const join = (a, b) => a.replace(/\/+$/, '') + '/' + String(b || '').replace(/^\/+/, '');

// Проксируем все ссылки на Unsplash через /u/ (чтобы не упираться в блокировки CDN)
function proxifyUnsplash(x) {
  if (Array.isArray(x)) return x.map(proxifyUnsplash);
  if (x && typeof x === 'object') {
    const y = {};
    for (const k in x) y[k] = proxifyUnsplash(x[k]);
    return y;
  }
  if (typeof x === 'string' && x.startsWith('https://images.unsplash.com/')) {
    return '/u/' + x.slice('https://images.unsplash.com/'.length);
  }
  return x;
}

/**
 * Performs GET request.
 * @param {string} endpoint API endpoint path, e.g. '/info'.
 * @param {*} onSuccess Callback on successful request.
 */
export function get(endpoint, onSuccess) {
  $.ajax({
    url: join(baseUrl, endpoint),
    dataType: 'json',
    success: result => onSuccess(proxifyUnsplash(result))
  });
}

/**
 * Performs POST request.
 * @param {string} endpoint API endpoint path, e.g. '/order'.
 * @param {string} data Request body in JSON format.
 * @param {*} onResult Callback on request result. In case of success, returns
 *                      result = { ok: true, data: <data-from-backend> }, otherwise
 *                      result = { ok: false, error: 'Something went wrong' }.
 */
export function post(endpoint, data, onResult) {
  $.ajax({
    type: 'POST',
    url: join(baseUrl, endpoint),
    data: data,
    contentType: 'application/json; charset=utf-8',
    dataType: 'json',
    success: result => onResult({ ok: true, data: proxifyUnsplash(result) }),
    error: xhr => onResult({ ok: false, error: 'Something went wrong.' })
  });
}