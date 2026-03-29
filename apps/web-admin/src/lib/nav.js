// nav.js - Two-level navigation, group/page switching, hash router

window.NAV_GROUPS = {
  system:   { label:'System',         pages:['system','tickets'],
              subs:[
                {p:'system',  label:'Main'},
                {p:'tickets', label:'Support Chat', badge:'supportBadge'},
              ]},
  network:  { label:'Network',        pages:['nodes','traffic','policies','jobs'],
              subs:[
                {p:'nodes',    label:'Nodes',            badge:'nbn'},
                {p:'traffic',  label:'Node Traffic'},
                {p:'policies', label:'Policies'},
                {p:'jobs',     label:'Jobs',             badge:'jbn'},
              ]},
  access:   { label:'Access Control', pages:['peers','registrations','users','devices','referral-codes','management','failban','audit'],
              subs:[
                {p:'peers',         label:'Peers',         badge:'peersBadge'},
                {p:'registrations', label:'Registrations', badge:'regBadge'},
                {p:'users',         label:'Users'},
                {p:'devices',       label:'Devices'},
                {p:'referral-codes',label:'Referral Pools'},
                {p:'management',    label:'Management'},
                {p:'failban',       label:'Fail2Ban',      dot:'red'},
                {p:'audit',         label:'Audit / Access'},
              ]},
  services: { label:'Services',       pages:['lust'],
              subs:[
                {p:'lust', label:'LuST'},
              ]},
  debug:    { label:'Debug',          pages:['apidebug','clientupdate'],
              subs:[
                {p:'apidebug',     label:'API Debug'},
                {p:'clientupdate', label:'Client Update'},
              ]},
};

window.PAGE_TO_GROUP = {};
Object.keys(window.NAV_GROUPS).forEach(function(g){
  window.NAV_GROUPS[g].pages.forEach(function(p){ window.PAGE_TO_GROUP[p] = g; });
});

window.CURRENT_GROUP = 'system';
window.CURRENT_PAGE  = 'system';

window.switchGroup = function switchGroup(groupName){
  var grp = window.NAV_GROUPS[groupName];
  if(!grp) return;
  window.CURRENT_GROUP = groupName;

  document.querySelectorAll('.nav-group-tab').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-g') === groupName);
  });

  var subBar = document.getElementById('navSub');
  subBar.innerHTML = '';

  if(!grp.subs.length){
    window.showPage(grp.pages[0]);
    return;
  }

  grp.subs.forEach(function(sub){
    var el = document.createElement('div');
    el.className = 'nav-sub-item';
    el.setAttribute('data-p', sub.p);

    var label = document.createElement('span');
    label.textContent = sub.label;
    el.appendChild(label);

    if(sub.badge){
      var orig = document.getElementById(sub.badge);
      if(orig){
        var badge = orig.cloneNode(true);
        badge.id = sub.badge + '_sub';
        badge.className = orig.className;
        badge.style.cssText = orig.style.cssText;
        el.appendChild(badge);
      }
    }
    if(sub.dot === 'red'){
      var dot = document.createElement('span');
      dot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:var(--red);display:inline-block;margin-left:4px;';
      el.appendChild(dot);
    }

    el.addEventListener('click', function(){
      window.showPage(sub.p);
    });
    subBar.appendChild(el);
  });

  if(window.PAGE_TO_GROUP[window.CURRENT_PAGE] === groupName){
    window.showPage(window.CURRENT_PAGE);
  } else {
    window.showPage(grp.subs[0].p);
  }

  location.hash = '#/' + groupName;
};

window.showPage = function showPage(pageId){
  window.CURRENT_PAGE = pageId;

  document.querySelectorAll('.page').forEach(function(p){
    p.classList.toggle('active', p.id === 'page-' + pageId);
  });

  document.querySelectorAll('.nav-sub-item').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-p') === pageId);
  });

  var g = window.PAGE_TO_GROUP[pageId] || pageId;
  document.querySelectorAll('.nav-group-tab').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-g') === g);
  });

  if(pageId==='failban'){ window.refreshFailban?.().catch(function(){}); }
  if(pageId==='clientupdate'){ window.cuOnPageShow?.(); }
  if(pageId==='lust'){ window.refreshLustServices?.().catch(function(){}); }
  if(pageId==='tickets'){ window.loadSupportTickets?.(); window.startSupportTicketsRefresh?.(); if(window._supportTicketId) window._clearSupportUnread?.(window._supportTicketId); }
  else { window.stopSupportTicketsRefresh?.(); }

  var grpName = window.PAGE_TO_GROUP[pageId] || pageId;
  location.hash = '#/' + grpName + '/' + pageId;
};

document.addEventListener('DOMContentLoaded', function(){
  var hash = location.hash;
  if(!hash || hash === '#' || hash === '#/') return;
  var parts = hash.replace(/^#\//, '').split('/');
  var groupName = parts[0] || 'system';
  var pageId = parts[1] || null;
  if(window.NAV_GROUPS[groupName]){
    if(pageId && window.PAGE_TO_GROUP[pageId] === groupName){
      window.switchGroup(groupName);
      window.showPage(pageId);
    } else {
      window.switchGroup(groupName);
    }
  }
});

export var switchGroup = window.switchGroup;
export var showPage    = window.showPage;
