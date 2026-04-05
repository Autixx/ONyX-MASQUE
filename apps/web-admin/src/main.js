// ONyX Admin Panel - main entry point

import './lib/state.js';
import './lib/api.js';
import './lib/utils.js';
import './lib/modal.js';
import './lib/i18n.js';
import './lib/theme.js';
import './lib/login-canvas.js';
import './lib/nav.js';
import './lib/ws.js';

import './pages/system.js';
import './pages/nodes.js';
import './pages/traffic.js';
import './pages/policies.js';
import './pages/jobs.js';
import './pages/audit.js';
import './pages/topology.js';
import './pages/peers.js';
import './pages/registrations.js';
import './pages/users.js';
import './pages/devices.js';
import './pages/referral.js';
import './pages/management.js';
import './pages/failban.js';
import './pages/lust.js';
import './pages/tickets.js';
import './pages/apidebug.js';
import './pages/clientupdate.js';
import './pages/accessmatrix.js';

window.normalizeAdminRole = function normalizeAdminRole(role) {
  var value = String(role || '').trim().toLowerCase();
  if (value === 'viewer') return 'l2';
  if (value === 'operator') return 'l3';
  return value;
};

window.setAdminContext = function setAdminContext(me) {
  window.ADMIN_ME = me || null;
  var roles = (((me || {}).user || {}).roles || []).map(window.normalizeAdminRole).filter(Boolean);
  var seen = {};
  roles = roles.filter(function(item) {
    if (seen[item]) return false;
    seen[item] = true;
    return true;
  });
  window.ADMIN_ROLES = roles;
  window.ADMIN_ROLE_SET = {};
  roles.forEach(function(role) { window.ADMIN_ROLE_SET[role] = true; });
};

window.hasAnyAdminRole = function hasAnyAdminRole(roles) {
  var wanted = Array.isArray(roles) ? roles : [roles];
  return wanted.some(function(role) { return !!window.ADMIN_ROLE_SET[window.normalizeAdminRole(role)]; });
};

window.fmtBytes = function(mb) {
  if (mb == null) return '-';
  if (mb < 1024) return mb.toFixed(0) + ' MB';
  return (mb / 1024).toFixed(2) + ' GB';
};
window.fmtDate = function(v) {
  if (!v) return '-';
  var d = new Date(v);
  if (isNaN(d)) return v;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};
window.isExpired = function(v) {
  if (!v) return false;
  return new Date(v) < new Date();
};

window.refreshIdentityData = async function() {
  var loaders = {};
  function _queue(key, fn) {
    if (!fn || loaders[key]) return;
    loaders[key] = fn;
  }
  if (window.pageVisible?.('users')) {
    _queue('users', window.loadUsers?.());
    _queue('plans', window.loadPlans?.());
    _queue('subscriptions', window.loadSubscriptions?.());
  }
  if (window.pageVisible?.('management')) {
    _queue('plans', window.loadPlans?.());
    _queue('subscriptions', window.loadSubscriptions?.());
    _queue('transport', window.loadTransportPackages?.());
  }
  if (window.pageVisible?.('referral-codes')) _queue('referral', window.loadReferralCodes?.());
  if (window.pageVisible?.('devices')) _queue('devices', window.loadDevices?.());
  await Promise.all(Object.keys(loaders).map(function(key) { return loaders[key]; }));
};

window.loadData = async function() {
  var tasks = [];
  if (window.pageVisible?.('nodes')) tasks.push(window.refreshNodes?.());
  if (window.pageVisible?.('traffic')) tasks.push(window.refreshNodeTrafficSummary?.());
  if (window.pageVisible?.('lust')) tasks.push(window.refreshLustServices?.());
  if (window.pageVisible?.('policies')) tasks.push(window.refreshPolicies?.());
  if (window.pageVisible?.('jobs')) tasks.push(window.refreshJobs?.());
  if (window.pageVisible?.('audit')) tasks.push(window.refreshAudit?.());
  if (window.pageVisible?.('peers')) tasks.push(window.loadPeers?.());
  if (window.pageVisible?.('registrations')) tasks.push(window.loadRegistrations?.());
  if (window.pageVisible?.('tickets')) tasks.push(window.updateOpenTicketCount?.());
  tasks.push(window.refreshIdentityData?.());
  await Promise.all(tasks.filter(Boolean));
};

var _healthPollTimer = null;
window.startHealthPolling = function() {
  if (_healthPollTimer) clearInterval(_healthPollTimer);
  _healthPollTimer = setInterval(function() {
    window.refreshHealth?.().catch(function(err) {
      console.warn('health poll failed', err);
    });
  }, 15000);
};

window.isAuthenticated = false;

window.doLogin = async function() {
  var u = document.getElementById('iu').value.trim();
  var p = document.getElementById('ip').value;
  var err = document.getElementById('lerr');
  if (!u || !p) {
    err.textContent = window.LANG === 'ru' ? 'Р’РІРµРґРёС‚Рµ РёРјСЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Рё РїР°СЂРѕР»СЊ' : 'Enter username and password';
    return;
  }
  err.textContent = '';
  document.getElementById('lbtn').textContent = window.uiLiteral?.('AUTHENTICATING...') || 'AUTHENTICATING...';
  if (window.DEMO_MODE) {
    await new Promise(function(r) { setTimeout(r, 600); });
    window.DEMO_USER = u;
    await window.bootApp();
    return;
  }
  try {
    await window.apiFetch(window.API_PREFIX + '/auth/login', {
      method: 'POST',
      body: { username: u, password: p },
      redirectOn401: false,
    });
    await window.bootApp();
  } catch (e) {
    err.textContent = e && e.message ? e.message : (window.LANG === 'ru' ? 'РћС€РёР±РєР° Р°СѓС‚РµРЅС‚РёС„РёРєР°С†РёРё' : 'Authentication failed');
    document.getElementById('lbtn').textContent = window.uiLiteral?.('AUTHENTICATE') || 'AUTHENTICATE';
  }
};

window.bootApp = async function(sessionMe) {
  var username = window.DEMO_USER || 'admin';
  if (!window.DEMO_MODE) {
    var me = sessionMe;
    if (me === undefined) {
      me = await window.apiFetch(window.API_PREFIX + '/auth/me');
    }
    window.setAdminContext(me);
    username = me && me.user && me.user.username ? me.user.username : 'admin';
  } else {
    window.setAdminContext({ user: { roles: ['admin'] } });
  }
  window.isAuthenticated = true;
  document.getElementById('loginWrap').style.display = 'none';
  document.getElementById('appWrap').style.display = 'flex';
  document.getElementById('ubtn').textContent = username;
  window.refreshNavigationAccess?.();
  document.getElementById('lbtn').textContent = window.uiLiteral?.('AUTHENTICATE') || 'AUTHENTICATE';
  document.getElementById('lerr').textContent = '';

  if (window.DEMO_MODE) {
    window.NODES = window.DEMO_NODES;
    window.NODE_TRAFFIC = window.DEMO_NODES.map(function(n) {
      var used = Number(n.traffic_used_gb || 0);
      var limit = n.traffic_limit_gb != null ? Number(n.traffic_limit_gb) : null;
      return {
        node_id: n.id, node_name: n.name, node_status: n.status,
        traffic_limit_gb: limit, traffic_used_gb: used,
        usage_ratio: limit ? used / limit : null,
        cycle_started_at: n.registered_at, cycle_ends_at: null,
        traffic_suspended_at: limit && used >= limit ? new Date().toISOString() : null,
        traffic_suspension_reason: limit && used >= limit ? 'traffic_limit_exceeded' : null,
      };
    });
    window.JOBS = window.DEMO_JOBS;
    window.POLICIES = window.DEMO_POLICIES;
    window.DNS_P = window.DEMO_DNS;
    window.GEO_P = [];
    window.BALANCERS = [];
    window.REGISTRATIONS = window.DEMO_REGISTRATIONS;
    window.PEERS = window.DEMO_PEERS;
    window.renderPeers?.();
    window.updatePeersBadge?.();
    window.renderNodes?.(); window.renderNodeTraffic?.();
    window.renderPolicies?.(); window.renderJobs?.(); window.renderAudit?.(); window.renderElog?.();
    window.renderRegistrations?.(); window.updateRegBadge?.(); window.updateShellCounters?.();
    window.pushEv?.('system.connected', 'DEMO MODE - not connected to real backend');
    window.startDemoMetricsTicker?.();
    window.scheduleLocaleRefresh?.();
    return;
  }

  try {
    if (window.pageVisible?.('system')) {
      await window.refreshHealth?.();
    }
  }
  catch (err) { window.pushEv?.('system.error', 'initial health load failed: ' + String(err && err.message ? err.message : err)); }
  try { await window.loadData(); }
  catch (err) { window.pushEv?.('system.error', 'initial data load failed: ' + String(err && err.message ? err.message : err)); }

  if (window.pageVisible?.('system')) window.startHealthPolling();
  if (window.pageVisible?.('failban')) {
    window.startFailbanPolling?.();
    window.refreshFailban?.().catch(function() {});
  }
  if (window.pageVisible?.('jobs')) window.startJobsTicker?.();
  window.connectWS?.();
  window.scheduleLocaleRefresh?.();
};

document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('lbtn').addEventListener('click', window.doLogin);
  document.getElementById('ip').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') window.doLogin();
  });

  document.getElementById('logoutBtn').addEventListener('click', async function() {
    if (confirm(window.LANG === 'ru' ? 'Р’С‹Р№С‚Рё РёР· РїР°РЅРµР»Рё СѓРїСЂР°РІР»РµРЅРёСЏ ONyX?' : 'Logout from ONyX Control Plane?')) {
      try { await window.apiFetch(window.API_PREFIX + '/auth/logout', { method: 'POST', redirectOn401: false }); } catch (_) {}
      window.authRedirect('');
    }
  });

  var _modalMdOnOverlay = false;
  document.getElementById('modalClose').addEventListener('click', window.closeModal);
  document.getElementById('modal').addEventListener('mousedown', function(event) {
    _modalMdOnOverlay = !!(event.target && event.target.id === 'modal');
  });
  document.getElementById('modal').addEventListener('click', function(event) {
    if (_modalMdOnOverlay && event.target && event.target.id === 'modal') window.closeModal();
    _modalMdOnOverlay = false;
  });

  document.addEventListener('mousedown', function(event) {
    var dp = document.getElementById('dp');
    if (!dp || !dp.classList.contains('open')) return;
    if (dp.contains(event.target)) return;
    window.closeDP();
  }, true);

  try { var t = localStorage.getItem('onyx-theme'); if (t) window.setTheme(t); } catch (e) {}

  try {
    var savedLang = localStorage.getItem('onyx-lang');
    if (savedLang === 'ru' || savedLang === 'en') window.LANG = savedLang;
  } catch (e) {}
  document.querySelectorAll('.lang-btn').forEach(function(b) {
    b.classList.toggle('active', b.textContent.trim().toLowerCase() === window.LANG);
  });
  window.scheduleLocaleRefresh?.();

  var app = document.getElementById('appWrap');
  if (app && typeof MutationObserver !== 'undefined') {
    var obs = new MutationObserver(function(mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].type === 'childList') { window.scheduleLocaleRefresh?.(); break; }
      }
    });
    obs.observe(app, { childList: true, subtree: true });
  }

  var _btn = function(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
  _btn('btnAddNode',                 function(){ window.openNodeModal?.(); });
  _btn('btnAddRoutePolicy',          function(){ window.openRoutePolicyModal?.(); });
  _btn('btnAddDNSPolicy',            function(){ window.openDNSPolicyModal?.(); });
  _btn('btnAddGeoPolicy',            function(){ window.openGeoPolicyModal?.(); });
  _btn('btnAddBalancer',             function(){ window.openBalancerModal?.(); });
  _btn('btnAddUser',                 function(){ window.openUserModal?.(); });
  _btn('btnAddPlan',                 function(){ window.openPlanModal?.(); });
  _btn('btnAddTransportPackage',     function(){ window.openTransportPackageModal?.(); });
  _btn('btnAddLustService',          function(){ window.openLustServiceModal?.(); });
  _btn('btnCreateReferralPool',      function(){ window.openReferralPoolModal?.(); });

  (async function init() {
    if (window.DEMO_MODE) { window.authRedirect(''); return; }
    var me = null;
    try {
      me = await window.apiFetch(window.API_PREFIX + '/auth/me', { redirectOn401: false });
    } catch (_) {
      window.authRedirect('');
      return;
    }
    try {
      await window.bootApp(me);
    } catch (err) {
      window.isAuthenticated = true;
      document.getElementById('loginWrap').style.display = 'none';
      document.getElementById('appWrap').style.display = 'flex';
      window.pushEv?.('system.error', 'boot failed: ' + String(err && err.message ? err.message : err));
      window.scheduleLocaleRefresh?.();
    }
  })();
});
