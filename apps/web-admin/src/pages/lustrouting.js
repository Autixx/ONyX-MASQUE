window.refreshLustRouting = async function refreshLustRouting(){
  var results = await Promise.all([
    apiFetch(API_PREFIX + '/lust-egress-pools'),
    apiFetch(API_PREFIX + '/lust-route-maps'),
    window.refreshLustServices?.()
  ]);
  window.LUST_EGRESS_POOLS = Array.isArray(results[0]) ? results[0] : [];
  window.LUST_ROUTE_MAPS = Array.isArray(results[1]) ? results[1] : [];
  window.renderLustPools();
  window.renderLustRouteMaps();
};

window.renderLustPools = function renderLustPools(){
  var tb = document.getElementById('lustpoolstb');
  if(!tb) return;
  var items = window.LUST_EGRESS_POOLS || [];
  if(!items.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="7">No LuST egress pools.</td></tr>';
    return;
  }
  tb.innerHTML = items.map(function(pool){
    var members = Array.isArray(pool.resolved_members) ? pool.resolved_members : [];
    return '<tr onclick="showLustPool(\''+esc(pool.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(pool.name)+'</td>'
      +'<td>'+esc(pool.selection_strategy || 'hash')+'</td>'
      +'<td>'+esc(String((pool.members_json || []).length))+'</td>'
      +'<td>'+esc(members.map(function(item){ return item.service_name || item.service_id; }).join(', ') || '-')+'</td>'
      +'<td>'+sp(pool.enabled ? 'active' : 'disabled')+'</td>'
      +'<td>'+esc(pool.description || '-')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();openLustPoolModal(\''+esc(pool.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteLustPoolFlow(\''+esc(pool.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.renderLustRouteMaps = function renderLustRouteMaps(){
  var tb = document.getElementById('lustroutemapstb');
  if(!tb) return;
  var items = window.LUST_ROUTE_MAPS || [];
  if(!items.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="8">No LuST route maps.</td></tr>';
    return;
  }
  tb.innerHTML = items.map(function(routeMap){
    return '<tr onclick="showLustRouteMap(\''+esc(routeMap.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(routeMap.name)+'</td>'
      +'<td>'+esc(routeMap.gateway_service_name || routeMap.gateway_service_id || '-')+'</td>'
      +'<td>'+esc(routeMap.egress_pool_name || routeMap.egress_pool_id || '-')+'</td>'
      +'<td>'+esc(String(routeMap.priority || 100))+'</td>'
      +'<td>'+esc(routeMap.destination_country_code || 'ANY')+'</td>'
      +'<td>'+sp(routeMap.enabled ? 'active' : 'disabled')+'</td>'
      +'<td>'+esc(routeMap.description || '-')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();openLustRouteMapModal(\''+esc(routeMap.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteLustRouteMapFlow(\''+esc(routeMap.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.showLustPool = function showLustPool(id){
  var pool = lustEgressPoolById(id); if(!pool) return;
  var members = Array.isArray(pool.resolved_members) ? pool.resolved_members : [];
  openDP('LuST Pool ' + pool.name,
    rows([
      ['ID', pool.id],
      ['Name', pool.name],
      ['Strategy', pool.selection_strategy || 'hash'],
      ['Enabled', pool.enabled ? 'yes' : 'no'],
      ['Configured Members', String((pool.members_json || []).length)],
      ['Resolved Members', String(members.length)],
      ['Description', pool.description || '-']
    ])
    +'<div class="stitle">Resolved Members</div>'
    +'<div class="tw"><table><thead><tr><th>Service</th><th>Node</th><th>Host</th><th>Weight</th><th>Country</th></tr></thead><tbody>'
      +(members.length ? members.map(function(item){
        return '<tr>'
          +'<td>'+esc(item.service_name || item.service_id || '-')+'</td>'
          +'<td>'+esc(item.node_name || item.node_id || '-')+'</td>'
          +'<td class="m">'+esc(item.host || '-')+':'+esc(String(item.port || '-'))+'</td>'
          +'<td>'+esc(String(item.weight || 1))+'</td>'
          +'<td>'+esc(item.country_code || '-')+'</td>'
          +'</tr>';
      }).join('') : '<tr><td class="empty-state" colspan="5">No active egress members resolved.</td></tr>')
    +'</tbody></table></div>'
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="openLustPoolModal(\''+esc(pool.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteLustPoolFlow(\''+esc(pool.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'lust-pool', id:pool.id }
  );
};

window.showLustRouteMap = function showLustRouteMap(id){
  var routeMap = lustRouteMapById(id); if(!routeMap) return;
  openDP('LuST Route Map ' + routeMap.name,
    rows([
      ['ID', routeMap.id],
      ['Name', routeMap.name],
      ['Gateway', routeMap.gateway_service_name || routeMap.gateway_service_id || '-'],
      ['Egress Pool', routeMap.egress_pool_name || routeMap.egress_pool_id || '-'],
      ['Priority', String(routeMap.priority || 100)],
      ['Country', routeMap.destination_country_code || 'ANY'],
      ['Enabled', routeMap.enabled ? 'yes' : 'no'],
      ['Description', routeMap.description || '-']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="openLustRouteMapModal(\''+esc(routeMap.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteLustRouteMapFlow(\''+esc(routeMap.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'lust-route-map', id:routeMap.id }
  );
};

window.openLustPoolModal = function openLustPoolModal(poolId){
  var pool = poolId ? lustEgressPoolById(poolId) : null;
  var selected = {};
  (pool && Array.isArray(pool.members_json) ? pool.members_json : []).forEach(function(item){
    selected[item.service_id] = item.weight || 100;
  });
  var egressServices = (window.LUST_SERVICES || []).filter(function(service){
    return String(service.role || '').toLowerCase() === 'egress';
  });
  var memberRows = egressServices.map(function(service){
    var checked = Object.prototype.hasOwnProperty.call(selected, service.id);
    var weight = checked ? selected[service.id] : (service.selection_weight || 100);
    return '<label style="display:grid;grid-template-columns:20px 1fr 80px;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.06);">'
      +'<input type="checkbox" data-pool-member="1" data-service-id="'+esc(service.id)+'" '+(checked ? 'checked' : '')+'>'
      +'<span>'+esc(service.name)+' <span style="color:var(--t2)">['+esc(service.public_host || '-')+']</span></span>'
      +'<input class="mf-input" type="number" min="1" value="'+esc(String(weight))+'" data-pool-weight-for="'+esc(service.id)+'" style="padding:6px 8px;font-size:12px;">'
      +'</label>';
  }).join('') || '<div class="empty-state">No LuST egress services available.</div>';
  openModal(pool ? 'Edit LuST Pool' : 'New LuST Pool',
    '<form id="lustPoolForm"><div class="modal-grid">'
      +formInput('Name', 'name', pool ? pool.name : '', {required:true})
      +formSelect('Strategy', 'selection_strategy', pool ? (pool.selection_strategy || 'hash') : 'hash', [{value:'hash', label:'hash'}, {value:'ordered', label:'ordered'}], {help:'hash = sticky distribution, ordered = primary/fallback.'})
      +formCheckbox('Enabled', 'enabled', pool ? !!pool.enabled : true, {caption:'Pool enabled'})
      +formTextarea('Description', 'description', pool ? (pool.description || '') : '', {full:true})
      +'<div class="mf-row full"><label class="mf-label">Egress Members</label><div style="border:1px solid var(--br);border-radius:10px;padding:10px 12px;background:rgba(255,255,255,.02)">'+memberRows+'</div><div class="mf-help">Select one or more egress services and set per-member weights.</div></div>'
    +'</div></form>',
    {
      buttons:[
        {label:'Cancel', className:'btn', onClick:closeModal},
        {label:pool ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('lustPoolForm').requestSubmit(); }}
      ]
    }
  );
  bindModalForm('lustPoolForm', function(fd){ saveLustPoolForm(fd, poolId); });
};

window.saveLustPoolForm = async function saveLustPoolForm(fd, poolId){
  var members = [];
  document.querySelectorAll('input[data-pool-member="1"]').forEach(function(box){
    if(!box.checked) return;
    var serviceId = String(box.getAttribute('data-service-id') || '').trim();
    var weightEl = document.querySelector('input[data-pool-weight-for="'+serviceId.replace(/"/g,'\\"')+'"]');
    members.push({
      service_id: serviceId,
      weight: Math.max(1, parseInt(weightEl && weightEl.value, 10) || 100)
    });
  });
  var payload = {
    name: fd.get('name'),
    selection_strategy: fd.get('selection_strategy') || 'hash',
    enabled: window.checked(fd, 'enabled'),
    members_json: members,
    description: (fd.get('description') || '').trim() || null,
  };
  try{
    if(poolId){
      await apiFetch(API_PREFIX + '/lust-egress-pools/' + encodeURIComponent(poolId), { method:'PATCH', body:payload });
    }else{
      await apiFetch(API_PREFIX + '/lust-egress-pools', { method:'POST', body:payload });
    }
    closeModal();
    await refreshLustRouting();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.deleteLustPoolFlow = async function deleteLustPoolFlow(poolId){
  var pool = lustEgressPoolById(poolId);
  if(!confirm('Delete LuST egress pool ' + (pool ? pool.name : poolId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/lust-egress-pools/' + encodeURIComponent(poolId), { method:'DELETE' });
    closeDP();
    await refreshLustRouting();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.openLustRouteMapModal = function openLustRouteMapModal(routeMapId){
  var routeMap = routeMapId ? lustRouteMapById(routeMapId) : null;
  var gatewayOptions = (window.LUST_SERVICES || []).filter(function(service){
    var role = String(service.role || '').toLowerCase();
    return role === 'gate' || role === 'standalone';
  }).map(function(service){
    return { value: service.id, label: service.name + ' [' + (service.role || 'standalone') + ']' };
  });
  var poolOptions = (window.LUST_EGRESS_POOLS || []).map(function(pool){
    return { value: pool.id, label: pool.name };
  });
  openModal(routeMap ? 'Edit LuST Route Map' : 'New LuST Route Map',
    '<form id="lustRouteMapForm"><div class="modal-grid">'
      +formInput('Name', 'name', routeMap ? routeMap.name : '', {required:true})
      +formSelect('Gateway Service', 'gateway_service_id', routeMap ? routeMap.gateway_service_id : (gatewayOptions[0] ? gatewayOptions[0].value : ''), gatewayOptions, {help:'Client enters through this LuST gateway.'})
      +formSelect('Egress Pool', 'egress_pool_id', routeMap ? routeMap.egress_pool_id : (poolOptions[0] ? poolOptions[0].value : ''), poolOptions, {help:'Pool used for upstream egress placement.'})
      +formInput('Priority', 'priority', routeMap ? String(routeMap.priority || 100) : '100', {required:true, type:'number'})
      +formInput('Destination Country', 'destination_country_code', routeMap ? (routeMap.destination_country_code || '') : '', {help:'Optional ISO country code filter, for example FR.'})
      +formCheckbox('Enabled', 'enabled', routeMap ? !!routeMap.enabled : true, {caption:'Route map enabled'})
      +formTextarea('Description', 'description', routeMap ? (routeMap.description || '') : '', {full:true})
    +'</div></form>',
    {
      buttons:[
        {label:'Cancel', className:'btn', onClick:closeModal},
        {label:routeMap ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('lustRouteMapForm').requestSubmit(); }}
      ]
    }
  );
  bindModalForm('lustRouteMapForm', function(fd){ saveLustRouteMapForm(fd, routeMapId); });
};

window.saveLustRouteMapForm = async function saveLustRouteMapForm(fd, routeMapId){
  var payload = {
    name: fd.get('name'),
    gateway_service_id: fd.get('gateway_service_id'),
    egress_pool_id: fd.get('egress_pool_id'),
    priority: Math.max(1, parseInt(fd.get('priority'), 10) || 100),
    destination_country_code: (fd.get('destination_country_code') || '').trim().toUpperCase() || null,
    enabled: window.checked(fd, 'enabled'),
    description: (fd.get('description') || '').trim() || null,
  };
  try{
    if(routeMapId){
      await apiFetch(API_PREFIX + '/lust-route-maps/' + encodeURIComponent(routeMapId), { method:'PATCH', body:payload });
    }else{
      await apiFetch(API_PREFIX + '/lust-route-maps', { method:'POST', body:payload });
    }
    closeModal();
    await refreshLustRouting();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.deleteLustRouteMapFlow = async function deleteLustRouteMapFlow(routeMapId){
  var routeMap = lustRouteMapById(routeMapId);
  if(!confirm('Delete LuST route map ' + (routeMap ? routeMap.name : routeMapId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/lust-route-maps/' + encodeURIComponent(routeMapId), { method:'DELETE' });
    closeDP();
    await refreshLustRouting();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

export {};
