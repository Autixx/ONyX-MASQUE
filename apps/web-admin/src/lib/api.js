// api.js — API prefix, fetch wrapper, auth redirect

var API_PREFIX = '/api/v1';
window.API_PREFIX = API_PREFIX;

window.authRedirect = function authRedirect(message){
  window.isAuthenticated = false;
  window.disconnectWS();
  document.getElementById('appWrap').style.display = 'none';
  document.getElementById('loginWrap').style.display = 'flex';
  document.getElementById('ip').value = '';
  document.getElementById('lbtn').textContent = window.uiLiteral('AUTHENTICATE');
  document.getElementById('lerr').textContent = message || '';
  window.scheduleLocaleRefresh();
};

window.apiFetch = async function apiFetch(path, options){
  var opts = options || {};
  var fetchOptions = {
    method: opts.method || 'GET',
    credentials: 'include',
    headers: Object.assign({}, opts.headers || {})
  };
  if(opts.body !== undefined){
    fetchOptions.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    if(!fetchOptions.headers['Content-Type']){
      fetchOptions.headers['Content-Type'] = 'application/json';
    }
  }
  var response = await fetch(path, fetchOptions);
  if(response.status === 204){
    return null;
  }
  var text = await response.text();
  var payload = null;
  if(text){
    try { payload = JSON.parse(text); }
    catch(_){ payload = text; }
  }
  if(response.status === 401 && opts.redirectOn401 !== false){
    window.authRedirect('Session expired. Please sign in again.');
    throw new Error('Unauthorized');
  }
  if(!response.ok){
    var rawDetail = payload && payload.detail ? payload.detail : ('HTTP '+response.status);
    var formatDetail = function(detail){
      if(typeof detail === 'string'){ return detail; }
      if(Array.isArray(detail)){
        var parts = detail.map(function(item){
          if(item && typeof item === 'object'){
            var msg = item.msg || item.message || '';
            var loc = Array.isArray(item.loc) ? item.loc.filter(function(part){ return part !== 'body' && part !== 'query' && part !== 'path'; }).join('.') : '';
            if(msg){ return loc ? (loc + ': ' + msg) : msg; }
          }
          return typeof item === 'string' ? item : '';
        }).filter(Boolean);
        return parts.join('; ');
      }
      if(detail && typeof detail === 'object'){
        return detail.message || detail.detail || JSON.stringify(detail);
      }
      return String(detail || '');
    };
    var detail = formatDetail(rawDetail);
    var error = new Error(detail);
    error.status = response.status;
    error.payload = payload;
    error.detail = rawDetail;
    throw error;
  }
  return payload;
};

export {};
export var authRedirect = window.authRedirect;
export var apiFetch = window.apiFetch;
