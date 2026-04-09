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

window.stopHealthPolling = function() {
  if (_healthPollTimer) {
    clearInterval(_healthPollTimer);
    _healthPollTimer = null;
  }
};

window.PAGE_REFRESHERS = {
  system: function() {
    return Promise.all([
      window.refreshHealth?.(),
      window.updateOpenTicketCount?.(),
    ].filter(Boolean));
  },
  nodes: function() {
    return window.refreshNodes?.();
  },
  traffic: function() {
    return window.refreshNodeTrafficSummary?.();
  },
  failban: function() {
    return Promise.all([
      window.refreshNodes?.(),
      window.refreshFailban?.(),
    ].filter(Boolean));
  },
  topology: function() {
    if (!window.refreshTopology) return Promise.resolve();
    return window.refreshTopology().then(function() {
      return window.drawTopo?.();
    });
  },
  audit: function() {
    return window.refreshAudit?.();
  },
  jobs: function() {
    return window.refreshJobs?.();
  },
  lust: function() {
    return Promise.all([
      window.refreshLustServices?.(),
      window.loadPeers?.(),
    ].filter(Boolean));
  },
  policies: function() {
    return window.refreshPolicies?.();
  },
  clientupdate: function() {
    if (!window.cuOnPageShow) return Promise.resolve();
    return Promise.resolve(window.cuOnPageShow());
  },
  users: function() {
    return Promise.all([
      window.loadUsers?.(),
      window.loadPlans?.(),
      window.loadSubscriptions?.(),
    ].filter(Boolean));
  },
  peers: function() {
    return Promise.all([
      window.loadPeers?.(),
      window.refreshLustServices?.(),
    ].filter(Boolean));
  },
  devices: function() {
    return window.loadDevices?.();
  },
  registrations: function() {
    return Promise.all([
      window.loadRegistrations?.(),
      window.loadUsers?.(),
    ].filter(Boolean));
  },
  'referral-codes': function() {
    return window.loadReferralCodes?.();
  },
  management: function() {
    return Promise.all([
      window.loadUsers?.(),
      window.loadPlans?.(),
      window.loadSubscriptions?.(),
      window.loadTransportPackages?.(),
    ].filter(Boolean));
  },
  tickets: function() {
    return Promise.all([
      Promise.resolve(window.loadSupportTickets?.(true)),
      window.updateOpenTicketCount?.(),
    ].filter(Boolean));
  },
  apidebug: function() {
    return Promise.resolve();
  },
  'access-matrix': function() {
    return window.loadAccessMatrix?.();
  },
};

window.PAGE_WS_REFRESH_MAP = {
  'job.': ['jobs', 'system', 'nodes', 'topology'],
  'link.': ['topology'],
  'node.': ['nodes', 'topology', 'failban', 'system'],
  'node.traffic.': ['nodes', 'traffic', 'topology', 'system'],
  'registration.': ['registrations', 'users', 'management'],
  'peer.': ['peers', 'lust', 'management'],
  'lust_service.': ['lust', 'peers'],
  'lust_egress_pool.': ['lust', 'peers'],
  'lust_route_map.': ['lust', 'peers'],
  'user.': ['users', 'management', 'devices'],
  'subscription.': ['management', 'users'],
  'plan.': ['management', 'users'],
  'referral_code.': ['referral-codes', 'management'],
  'device.': ['devices', 'management', 'users'],
  'transport_package.': ['management', 'users'],
  'support.': ['tickets', 'system'],
  'access_rule.': ['access-matrix'],
  'audit.': ['audit'],
};

window._pageRefreshLocks = {};
window._pageRefreshPending = {};
window._pageRefreshTimers = {};
window._livePageRefreshTimer = null;
window.PAGE_LIVE_REFRESH_INTERVAL_MS = 10000;

window.refreshPageNow = async function refreshPageNow(pageId, options) {
  var opts = options || {};
  var refresher = window.PAGE_REFRESHERS[pageId];
  if (!refresher || !window.pageVisible?.(pageId) || !window.isAuthenticated) {
    return;
  }
  if (window._pageRefreshLocks[pageId]) {
    window._pageRefreshPending[pageId] = true;
    return;
  }
  window._pageRefreshLocks[pageId] = true;
  try {
    await refresher();
  } catch (err) {
    if (!opts.silent) {
      console.warn('page refresh failed', pageId, err);
    }
  } finally {
    window._pageRefreshLocks[pageId] = false;
    if (window._pageRefreshPending[pageId]) {
      window._pageRefreshPending[pageId] = false;
      window.refreshPageNow(pageId, opts);
    }
  }
};

window.queuePageRefresh = function queuePageRefresh(pageId, delayMs) {
  if (!window.pageVisible?.(pageId) || !window.isAuthenticated) return;
  var delay = Math.max(0, Number(delayMs || 0));
  if (window._pageRefreshTimers[pageId]) {
    clearTimeout(window._pageRefreshTimers[pageId]);
  }
  window._pageRefreshTimers[pageId] = setTimeout(function() {
    window._pageRefreshTimers[pageId] = null;
    window.refreshPageNow(pageId, { silent: true });
  }, delay);
};

window.queuePagesRefresh = function queuePagesRefresh(pageIds, delayMs) {
  (pageIds || []).forEach(function(pageId) {
    window.queuePageRefresh(pageId, delayMs);
  });
};

window.resolveEventPages = function resolveEventPages(eventType) {
  var type = String(eventType || '');
  var pages = [];
  Object.keys(window.PAGE_WS_REFRESH_MAP).forEach(function(prefix) {
    if (type.indexOf(prefix) !== 0) return;
    pages = pages.concat(window.PAGE_WS_REFRESH_MAP[prefix]);
  });
  if (type === 'audit.event') pages.push('audit');
  if (type === 'system.connected' || type === 'system.error') pages.push('system');
  var seen = {};
  return pages.filter(function(pageId) {
    if (!pageId || seen[pageId]) return false;
    seen[pageId] = true;
    return true;
  });
};

window.startLivePageRefresh = function startLivePageRefresh() {
  if (window._livePageRefreshTimer) clearInterval(window._livePageRefreshTimer);
  window._livePageRefreshTimer = setInterval(function() {
    if (!window.isAuthenticated || document.hidden) return;
    if (window.CURRENT_PAGE) {
      window.refreshPageNow(window.CURRENT_PAGE, { silent: true });
    }
  }, window.PAGE_LIVE_REFRESH_INTERVAL_MS);
};

window.stopLivePageRefresh = function stopLivePageRefresh() {
  if (window._livePageRefreshTimer) {
    clearInterval(window._livePageRefreshTimer);
    window._livePageRefreshTimer = null;
  }
};

window.handlePageLifecycle = function handlePageLifecycle(pageId) {
  var current = String(pageId || '');
  if (current === 'system') window.startHealthPolling();
  else window.stopHealthPolling?.();

  if (current === 'failban') window.startFailbanPolling?.();
  else window.stopFailbanPolling?.();

  if (current === 'jobs') window.startJobsTicker?.();
  else window.stopJobsTicker?.();

  if (current === 'tickets') window.startSupportTicketsRefresh?.();
  else window.stopSupportTicketsRefresh?.();

  if (current) {
    window.queuePageRefresh(current, 0);
  }
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

  window.handlePageLifecycle?.(window.CURRENT_PAGE);
  window.startLivePageRefresh?.();
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

  document.addEventListener('visibilitychange', function() {
    if (!document.hidden && window.isAuthenticated && window.CURRENT_PAGE) {
      window.queuePageRefresh(window.CURRENT_PAGE, 0);
    }
  });
});
