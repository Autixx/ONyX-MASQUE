// nav.js - role-aware two-level navigation and hash router

window.NAV_GROUPS = {
  infrastructure: {
    label: 'Infrastructure',
    pages: ['system', 'traffic', 'failban', 'topology', 'audit'],
    visible_for: ['l2', 'l3', 'audit', 'admin'],
    subs: [
      { p: 'system',   label: 'Overview',   visible_for: ['l2', 'l3', 'audit', 'admin'] },
      { p: 'traffic',  label: 'Traffic',    visible_for: ['l2', 'l3', 'audit', 'admin'] },
      { p: 'failban',  label: 'Security',   visible_for: ['l2', 'l3', 'audit', 'admin'], dot: 'red' },
      { p: 'topology', label: 'Topology',   visible_for: ['l2', 'l3', 'audit', 'admin'] },
      { p: 'audit',    label: 'Audit',      visible_for: ['audit', 'admin'] },
    ],
  },
  operations: {
    label: 'Operations',
    pages: ['nodes', 'jobs', 'lust', 'policies', 'clientupdate'],
    visible_for: ['l2', 'l3', 'admin'],
    subs: [
      { p: 'nodes',        label: 'Nodes',          badge: 'nbn', visible_for: ['l2', 'l3', 'admin'] },
      { p: 'jobs',         label: 'Deployments',    badge: 'jbn', visible_for: ['l2', 'l3', 'admin'] },
      { p: 'lust',         label: 'LuST',           visible_for: ['l2', 'l3', 'admin'] },
      { p: 'policies',     label: 'Routing',        visible_for: ['l3', 'admin'] },
      { p: 'clientupdate', label: 'Client Updates', visible_for: ['l3', 'admin'] },
    ],
  },
  management: {
    label: 'Management',
    pages: ['users', 'peers', 'devices', 'registrations', 'referral-codes', 'management'],
    visible_for: ['l1', 'l2', 'l3', 'admin'],
    subs: [
      { p: 'users',          label: 'Users',          visible_for: ['l2', 'l3', 'admin'] },
      { p: 'peers',          label: 'Peers',          badge: 'peersBadge', visible_for: ['l2', 'l3', 'admin'] },
      { p: 'devices',        label: 'Devices',        visible_for: ['l2', 'l3', 'admin'] },
      { p: 'registrations',  label: 'Registrations',  badge: 'regBadge', visible_for: ['l1', 'l2', 'l3', 'admin'] },
      { p: 'referral-codes', label: 'Referral',       visible_for: ['l2', 'l3', 'admin'] },
      { p: 'management',     label: 'Billing / Access', visible_for: ['l2', 'l3', 'admin'] },
    ],
  },
  support: {
    label: 'Support',
    pages: ['tickets', 'apidebug'],
    visible_for: ['l1', 'l2', 'l3', 'audit', 'admin'],
    subs: [
      { p: 'tickets',  label: 'Support Chat', badge: 'supportBadge', visible_for: ['l1', 'l2', 'l3', 'admin'] },
      { p: 'apidebug', label: 'Debug',        visible_for: ['l2', 'l3', 'audit', 'admin'] },
    ],
  },
  admin: {
    label: 'Admin',
    pages: ['access-matrix'],
    visible_for: ['admin'],
    subs: [
      { p: 'access-matrix', label: 'Access Matrix', visible_for: ['admin'] },
    ],
  },
};

window.PAGE_TO_GROUP = {};
Object.keys(window.NAV_GROUPS).forEach(function(groupName){
  window.NAV_GROUPS[groupName].pages.forEach(function(pageId){
    window.PAGE_TO_GROUP[pageId] = groupName;
  });
});

window.CURRENT_GROUP = 'infrastructure';
window.CURRENT_PAGE = 'system';

window.navSubVisible = function navSubVisible(sub) {
  var roles = sub && sub.visible_for ? sub.visible_for : [];
  return !roles.length || window.hasAnyAdminRole?.(roles);
};

window.navGroupVisible = function navGroupVisible(groupName) {
  var group = window.NAV_GROUPS[groupName];
  if (!group) return false;
  if (group.visible_for && group.visible_for.length && !window.hasAnyAdminRole?.(group.visible_for)) {
    return false;
  }
  return (group.subs || []).some(window.navSubVisible);
};

window.firstVisibleGroup = function firstVisibleGroup() {
  return Object.keys(window.NAV_GROUPS).find(function(groupName) {
    return window.navGroupVisible(groupName);
  }) || 'infrastructure';
};

window.firstVisiblePageInGroup = function firstVisiblePageInGroup(groupName) {
  var group = window.NAV_GROUPS[groupName];
  if (!group) return null;
  var sub = (group.subs || []).find(window.navSubVisible);
  return sub ? sub.p : null;
};

window.pageVisible = function pageVisible(pageId) {
  var groupName = window.PAGE_TO_GROUP[pageId];
  if (!groupName || !window.navGroupVisible(groupName)) return false;
  var group = window.NAV_GROUPS[groupName];
  return !!(group.subs || []).find(function(sub) { return sub.p === pageId && window.navSubVisible(sub); });
};

window.refreshNavigationAccess = function refreshNavigationAccess() {
  document.querySelectorAll('.nav-group-tab').forEach(function(el) {
    var groupName = el.getAttribute('data-g');
    var group = window.NAV_GROUPS[groupName];
    var visible = !!group && window.navGroupVisible(groupName);
    el.style.display = visible ? '' : 'none';
    if (visible) {
      var label = el.querySelector('.nav-group-label');
      if (!label) {
        el.textContent = group.label;
      } else {
        label.textContent = group.label;
      }
    }
  });
  var targetGroup = window.navGroupVisible(window.CURRENT_GROUP) ? window.CURRENT_GROUP : window.firstVisibleGroup();
  window.switchGroup(targetGroup);
};

window.switchGroup = function switchGroup(groupName){
  if (!window.navGroupVisible(groupName)) {
    groupName = window.firstVisibleGroup();
  }
  var group = window.NAV_GROUPS[groupName];
  if (!group) return;
  window.CURRENT_GROUP = groupName;

  document.querySelectorAll('.nav-group-tab').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-g') === groupName);
  });

  var subBar = document.getElementById('navSub');
  if (!subBar) return;
  subBar.innerHTML = '';

  var visibleSubs = (group.subs || []).filter(window.navSubVisible);
  visibleSubs.forEach(function(sub){
    var el = document.createElement('div');
    el.className = 'nav-sub-item';
    el.setAttribute('data-p', sub.p);

    var label = document.createElement('span');
    label.textContent = sub.label;
    el.appendChild(label);

    if (sub.badge) {
      var orig = document.getElementById(sub.badge);
      if (orig) {
        var badge = orig.cloneNode(true);
        badge.id = sub.badge + '_sub';
        badge.className = orig.className;
        badge.style.cssText = orig.style.cssText;
        el.appendChild(badge);
      }
    }
    if (sub.dot === 'red') {
      var dot = document.createElement('span');
      dot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:var(--red);display:inline-block;margin-left:4px;';
      el.appendChild(dot);
    }

    el.addEventListener('click', function() {
      window.showPage(sub.p);
    });
    subBar.appendChild(el);
  });

  var pageToShow = window.pageVisible(window.CURRENT_PAGE) && window.PAGE_TO_GROUP[window.CURRENT_PAGE] === groupName
    ? window.CURRENT_PAGE
    : (visibleSubs[0] ? visibleSubs[0].p : null);
  if (pageToShow) {
    window.showPage(pageToShow);
  }

  location.hash = '#/' + groupName;
};

window.showPage = function showPage(pageId){
  if (!window.pageVisible(pageId)) {
    var fallbackGroup = window.firstVisibleGroup();
    var fallbackPage = window.firstVisiblePageInGroup(fallbackGroup);
    if (!fallbackPage) return;
    pageId = fallbackPage;
  }
  window.CURRENT_PAGE = pageId;

  document.querySelectorAll('.page').forEach(function(page){
    page.classList.toggle('active', page.id === 'page-' + pageId);
  });

  document.querySelectorAll('.nav-sub-item').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-p') === pageId);
  });

  var groupName = window.PAGE_TO_GROUP[pageId] || pageId;
  window.CURRENT_GROUP = groupName;
  document.querySelectorAll('.nav-group-tab').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-g') === groupName);
  });

  if (pageId === 'failban') { window.refreshFailban?.().catch(function(){}); }
  if (pageId === 'clientupdate') { window.cuOnPageShow?.(); }
  if (pageId === 'lust') { window.refreshLustServices?.().catch(function(){}); }
  if (pageId === 'topology') { window.refreshTopology?.().then(window.drawTopo).catch(function(){}); }
  if (pageId === 'access-matrix') { window.loadAccessMatrix?.().catch(function(){}); }
  if (pageId === 'tickets') {
    window.loadSupportTickets?.();
    window.startSupportTicketsRefresh?.();
    if (window._supportTicketId) window._clearSupportUnread?.(window._supportTicketId);
  } else {
    window.stopSupportTicketsRefresh?.();
  }

  location.hash = '#/' + groupName + '/' + pageId;
};

document.addEventListener('DOMContentLoaded', function(){
  var hash = location.hash;
  if (!hash || hash === '#' || hash === '#/') return;
  var parts = hash.replace(/^#\//, '').split('/');
  var groupName = parts[0] || window.firstVisibleGroup();
  var pageId = parts[1] || null;
  if (!window.NAV_GROUPS[groupName]) return;
  if (pageId && window.PAGE_TO_GROUP[pageId] === groupName) {
    window.switchGroup(groupName);
    window.showPage(pageId);
  } else {
    window.switchGroup(groupName);
  }
});

export var switchGroup = window.switchGroup;
export var showPage = window.showPage;
