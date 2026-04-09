// Page module - all functions exposed as window globals

function _peerRouteOverride(peer){
  var raw = peer && (peer.lust_route_override || peer.lust_route_override_json) || {};
  return {
    route_map_id: raw && raw.route_map_id ? raw.route_map_id : '',
    egress_pool_id: raw && raw.egress_pool_id ? raw.egress_pool_id : '',
    egress_service_id: raw && raw.egress_service_id ? raw.egress_service_id : ''
  };
}

function _peerRouteOverrideSummary(peer){
  var override = _peerRouteOverride(peer);
  var parts = [];
  if(override.route_map_id){
    var routeMap = (window.LUST_ROUTE_MAPS || []).find(function(item){ return item.id === override.route_map_id; });
    parts.push('map: ' + (routeMap ? routeMap.name : override.route_map_id));
  }
  if(override.egress_pool_id){
    var pool = (window.LUST_EGRESS_POOLS || []).find(function(item){ return item.id === override.egress_pool_id; });
    parts.push('pool: ' + (pool ? pool.name : override.egress_pool_id));
  }
  if(override.egress_service_id){
    var service = lustServiceById(override.egress_service_id);
    parts.push('egress: ' + (service ? service.name : override.egress_service_id));
  }
  return parts.join(' | ') || '-';
}

window.loadPeerRoutingOptions = async function loadPeerRoutingOptions(){
  var tasks = [];
  if(!(window.LUST_SERVICES || []).length) tasks.push(window.refreshLustServices?.());
  tasks.push(apiFetch(API_PREFIX + '/lust-route-maps').then(function(data){ window.LUST_ROUTE_MAPS = Array.isArray(data) ? data : []; }));
  tasks.push(apiFetch(API_PREFIX + '/lust-egress-pools').then(function(data){ window.LUST_EGRESS_POOLS = Array.isArray(data) ? data : []; }));
  await Promise.all(tasks.filter(Boolean));
};

window.refreshPeerRouteOverrideOptions = function refreshPeerRouteOverrideOptions(){
  var serviceSel = document.getElementById('peerLustServiceId');
  var routeMapSel = document.getElementById('peerRouteMapId');
  var poolSel = document.getElementById('peerEgressPoolId');
  if(!serviceSel || !routeMapSel || !poolSel) return;
  var serviceId = serviceSel.value || '';
  var routeMaps = (window.LUST_ROUTE_MAPS || []).filter(function(item){
    return !serviceId || item.gateway_service_id === serviceId;
  });
  var poolSeen = {};
  var poolIds = routeMaps.map(function(item){ return item.egress_pool_id; }).filter(function(id){
    if(!id || poolSeen[id]) return false;
    poolSeen[id] = true;
    return true;
  });
  var pools = (window.LUST_EGRESS_POOLS || []).filter(function(item){ return poolIds.indexOf(item.id) !== -1; });
  var currentRouteMap = routeMapSel.value || '';
  var currentPool = poolSel.value || '';

  routeMapSel.innerHTML = '<option value="">Auto</option>' + routeMaps.map(function(item){
    return '<option value="'+esc(item.id)+'"'+(item.id === currentRouteMap ? ' selected' : '')+'>'+esc(item.name)+'</option>';
  }).join('');
  if(currentRouteMap && !routeMaps.some(function(item){ return item.id === currentRouteMap; })){
    routeMapSel.value = '';
  }

  poolSel.innerHTML = '<option value="">Auto</option>' + pools.map(function(item){
    return '<option value="'+esc(item.id)+'"'+(item.id === currentPool ? ' selected' : '')+'>'+esc(item.name)+'</option>';
  }).join('');
  if(currentPool && !pools.some(function(item){ return item.id === currentPool; })){
    poolSel.value = '';
  }
};

window.loadPeers = async function loadPeers(){
  try{
    var data = await apiFetch(API_PREFIX + '/peers');
    PEERS = Array.isArray(data) ? data : (data && data.items ? data.items : []);
  }catch(e){
    if(!PEERS.length) PEERS = [];
  }
  renderPeers();
  updatePeersBadge();
  window.renderLustServices?.();
};

window.renderPeers = function renderPeers(){
  var tb = document.getElementById('peerstb');
  if(!tb) return;

  // Populate node filter
  var nodeFilter = document.getElementById('peerNodeFilter');
  if(nodeFilter && nodeFilter.options.length <= 1){
    NODES.forEach(function(n){
      var opt = document.createElement('option');
      opt.value = n.id; opt.textContent = n.name;
      nodeFilter.appendChild(opt);
    });
  }

  var search = (document.getElementById('peerSearch')||{}).value || '';
  var nodeId = (document.getElementById('peerNodeFilter')||{}).value || '';
  search = search.trim().toLowerCase();

  var rows = PEERS.filter(function(p){
    if(nodeId && p.node_id !== nodeId) return false;
    if(search){
      var hay = [p.username,p.email,p.last_ip,p.node_id].join(' ').toLowerCase();
      if(hay.indexOf(search) === -1) return false;
    }
    return true;
  });

  if(!rows.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="9">No peers found.</td></tr>';
    return;
  }

  tb.innerHTML = rows.map(function(p){
    var node = NODES.find(function(n){ return n.id === p.node_id; });
    var nodeName = node ? node.name : (p.node_id || '-');
    var expired = isExpired(p.config_expires_at);
    var expClass = expired ? 'style="color:var(--red)"' : '';
    return '<tr onclick="showPeerDetail(\''+esc(p.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(p.username||'-')+'</td>'
      +'<td style="color:var(--t1)">'+esc(p.email||'-')+'</td>'
      +'<td><span class="pill pb">'+esc(nodeName)+'</span></td>'
      +'<td style="color:var(--t1);font-size:13px;">'+fmtDate(p.registered_at)+'</td>'
      +'<td '+expClass+'>'+fmtDate(p.config_expires_at)+(expired?' <span class="pill pr">expired</span>':'')+'</td>'
      +'<td class="m">'+esc(p.last_ip||'-')+'</td>'
      +'<td style="color:var(--t1)">'+fmtBytes(p.traffic_24h_mb)+'</td>'
      +'<td style="color:var(--t1)">'+fmtBytes(p.traffic_month_mb)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();openPeerConfig(\''+esc(p.id)+'\')">CONFIG</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();revokePeer(\''+esc(p.id)+'\')">REVOKE</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.updatePeersBadge = function updatePeersBadge(){
  var badge = document.getElementById('peersBadge');
  if(!badge) return;
  badge.textContent = String(PEERS.length);
  if(PEERS.length > 0){ badge.style.display = ''; }
  else { badge.style.display = 'none'; }
};

window.openPeerConfig = async function openPeerConfig(peerId){
  var p = PEERS.find(function(x){ return x.id === peerId; });
  try{
    var data = await apiFetch(API_PREFIX + '/peers/' + encodeURIComponent(peerId));
    p = data || p;
    await window.loadPeerRoutingOptions?.();
  }catch(e){
    alert('Could not load peer config.');
    return;
  }
  var config = p && p.config ? p.config : null;
  var routeOverride = _peerRouteOverride(p);
  var serviceOptions = [{value:'', label:'- auto gateway -'}].concat((window.LUST_SERVICES || []).filter(function(service){
    var role = String(service.role || '').toLowerCase();
    return role === 'gate' || role === 'standalone';
  }).map(function(service){
    return { value: service.id, label: service.name + ' [' + (service.role || 'standalone') + ']' };
  }));
  var egressOptions = [{value:'', label:'- auto egress -'}].concat((window.LUST_SERVICES || []).filter(function(service){
    return String(service.role || '').toLowerCase() === 'egress';
  }).map(function(service){
    return { value: service.id, label: service.name };
  }));
  openModal('Peer Config',
    '<div class="modal-grid one">'
      +'<div class="form-group full">'
        +'<textarea id="peerConfigText" style="width:100%;height:320px;font-family:monospace;font-size:12px;">'+esc(config || '')+'</textarea>'
      +'</div>'
      +formSelect('Gateway Service', 'peerLustServiceId', p && p.lust_service_id ? p.lust_service_id : '', serviceOptions, {full:true, help:'Client enters through this LuST gateway.'})
      +formSelect('Forced Route Map', 'peerRouteMapId', routeOverride.route_map_id, [{value:'', label:'Auto'}], {full:true, help:'Optional operator pinning to a concrete gateway route map.'})
      +formSelect('Forced Egress Pool', 'peerEgressPoolId', routeOverride.egress_pool_id, [{value:'', label:'Auto'}], {full:true, help:'Optional pool constraint inside the selected gateway.'})
      +formSelect('Forced Egress Service', 'peerEgressServiceId', routeOverride.egress_service_id, egressOptions, {full:true, help:'Optional hard pin to a specific egress node.'})
    +'</div>',
    {buttons:[
      {label:'Close', className:'btn', onClick:closeModal},
      {label:'Save', className:'btn pri', onClick:function(){ savePeerConfig(peerId); }}
    ]}
  );
  var serviceSelect = document.getElementById('peerLustServiceId');
  if(serviceSelect){
    serviceSelect.addEventListener('change', window.refreshPeerRouteOverrideOptions);
  }
  window.refreshPeerRouteOverrideOptions?.();
};

window.savePeerConfig = async function savePeerConfig(peerId){
  var el = document.getElementById('peerConfigText');
  var serviceSel = document.getElementById('peerLustServiceId');
  var routeMapSel = document.getElementById('peerRouteMapId');
  var poolSel = document.getElementById('peerEgressPoolId');
  var egressSel = document.getElementById('peerEgressServiceId');
  if(!el) return;
  var routeOverride = {};
  if(routeMapSel && routeMapSel.value) routeOverride.route_map_id = routeMapSel.value;
  if(poolSel && poolSel.value) routeOverride.egress_pool_id = poolSel.value;
  if(egressSel && egressSel.value) routeOverride.egress_service_id = egressSel.value;
  try{
    await apiFetch(API_PREFIX + '/peers/' + encodeURIComponent(peerId) + '/config', {
      method:'PUT', body:{
        config: el.value,
        lust_service_id: serviceSel && serviceSel.value ? serviceSel.value : null,
        lust_route_override: routeOverride
      }
    });
    closeModal();
    await loadPeers();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.revokePeer = async function revokePeer(peerId){
  var p = PEERS.find(function(x){ return x.id === peerId; });
  var label = p ? (p.username || p.email || p.id) : peerId;
  if(!confirm('Revoke peer "' + label + '"? This will remove their VPN access.')) return;
  try{
    await apiFetch(API_PREFIX + '/peers/' + encodeURIComponent(peerId) + '/revoke', { method:'POST' });
    closeDP();
    await loadPeers();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.showPeerDetail = function showPeerDetail(id){
  var p = PEERS.find(function(x){ return x.id===id; });
  if(!p) return;
  var node = NODES.find(function(n){ return n.id === p.node_id; });
  var user = USERS.find(function(u){ return u.email === p.email; });
  var sub = user ? SUBSCRIPTIONS.find(function(s){ return s.user_id === user.id && s.status === 'active'; }) : null;
  var pkg = user ? TRANSPORT_PACKAGES.find(function(t){ return t.user_id === user.id; }) : null;
  openDP(p.username || 'Peer',
    rows([
      ['ID', p.id],
      ['Login', p.username||'-'],
      ['E-mail', p.email||'-'],
      ['Node', node ? node.name : (p.node_id||'-')],
      ['Subscription', sub ? planNameById(sub.plan_id) + ' (' + sub.status + ')' : '-'],
      ['Transport Pkg', pkg ? (pkg.name || pkg.id) : '-'],
      ['Registered', fmtDate(p.registered_at)],
      ['Config Expires', fmtDate(p.config_expires_at)],
      ['Last IP', p.last_ip||'-'],
      ['Traffic 24h', fmtBytes(p.traffic_24h_mb)],
      ['Traffic Month', fmtBytes(p.traffic_month_mb)],
      ['LuST Route Pin', _peerRouteOverrideSummary(p)],
    ])
    +'<div class="dp-actions">'
      +'<button class="btn pri" onclick="openPeerConfig(\''+esc(p.id)+'\')">VIEW CONFIG</button>'
      +'<button class="btn red" onclick="revokePeer(\''+esc(p.id)+'\')">REVOKE</button>'
    +'</div>'
  );
};

export {};
