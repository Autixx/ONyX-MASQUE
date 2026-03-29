var _SCHED_KEYS = ['mon','tue','wed','thu','fri','sat','sun'];
var _SCHED_LABELS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
var _userPkgShouldReconcile = false;

function subscriptionAccessSummary(obj) {
  if(!obj || !obj.access_window_enabled) return 'Always';
  var mask = Number(obj.access_days_mask != null ? obj.access_days_mask : 127);
  var days = _SCHED_LABELS.filter(function(_, i){ return !!(mask & (1 << i)); });
  var timeStr = obj.access_window_start_local && obj.access_window_end_local ? (' ' + obj.access_window_start_local + 'вЂ“' + obj.access_window_end_local) : '';
  return days.length === 7 ? ('Every day' + timeStr) : (days.join(', ') + timeStr);
}

window.loadPlans = async function(){
  PLANS = await apiFetch(API_PREFIX + '/plans');
  window.renderPlans();
  window.updateUserSubFilter();
};

window.loadSubscriptions = async function(){
  SUBSCRIPTIONS = await apiFetch(API_PREFIX + '/subscriptions');
  window.renderSubscriptions();
};

window.loadTransportPackages = async function(){
  TRANSPORT_PACKAGES = await apiFetch(API_PREFIX + '/transport-packages');
  window.renderTransportPackages();
};

window.refreshIdentityData = async function(){
  await Promise.all([loadUsers(), loadPlans(), loadSubscriptions(), loadReferralCodes(), loadDevices(), loadTransportPackages()]);
};

window.updateUserSubFilter = function(){
  var sel = document.getElementById('userSubFilter');
  if(!sel) return;
  var cur = sel.value;
  sel.innerHTML = '<option value="">All subscriptions</option>'
    + PLANS.map(function(p){ return '<option value="'+esc(p.id)+'"'+(p.id===cur?' selected':'')+'>'+esc(p.name)+'</option>'; }).join('');
};

window.renderPlans = function(){
  var tb = document.getElementById('plantb');
  if(!tb) return;
  if(!PLANS.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="7">No subscriptions.</td></tr>';
    return;
  }
  tb.innerHTML = PLANS.map(function(p){
    var profile = p.transport_package_id ? transportPackageById(p.transport_package_id) : null;
    return '<tr>'
      +'<td class="m">'+esc(p.name)+'</td>'
      +'<td>'+esc(p.billing_mode)+'</td>'
      +'<td>'+esc(profile ? (profile.name || profile.id) : '-')+'</td>'
      +'<td>'+esc(String(p.default_device_limit || '-'))+'</td>'
      +'<td>'+esc(subscriptionAccessSummary(p))+'</td>'
      +'<td>'+(p.enabled ? sp('active') : sp('deleted'))+'</td>'
      +'<td style="display:flex;gap:5px;">'
      +'<button class="btn sm" onclick="showPlan(\''+esc(p.id)+'\')">VIEW</button>'
      +'<button class="btn sm" onclick="openPlanModal(\''+esc(p.id)+'\')">EDIT</button>'
      +'<button class="btn sm red" onclick="deletePlanFlow(\''+esc(p.id)+'\')">DEL</button>'
      +'</td></tr>';
  }).join('');
};

window.renderSubscriptions = function(){
  var tb = document.getElementById('subtb');
  if(!tb) return;
  if(!SUBSCRIPTIONS.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="6">No subscriptions.</td></tr>';
    return;
  }
  tb.innerHTML = SUBSCRIPTIONS.map(function(s){
    return '<tr>'
      +'<td class="m">'+esc(userNameById(s.user_id))+'</td>'
      +'<td>'+esc(planNameById(s.plan_id))+'</td>'
      +'<td>'+sp(s.status)+'</td>'
      +'<td>'+esc(s.expires_at ? new Date(s.expires_at).toLocaleString() : 'lifetime')+'</td>'
      +'<td>'+esc(subscriptionAccessSummary(s))+'</td>'
      +'<td style="display:flex;gap:5px;">'
      +'<button class="btn sm" onclick="showSubscription(\''+esc(s.id)+'\')">VIEW</button>'
      +'<button class="btn sm" onclick="openSubscriptionModal(\''+esc(s.id)+'\')">EDIT</button>'
      +'<button class="btn sm red" onclick="deleteSubscriptionFlow(\''+esc(s.id)+'\')">DEL</button>'
      +'</td></tr>';
  }).join('');
};

window.renderTransportPackages = function(){
  var tb = document.getElementById('tptb');
  if(!tb) return;
  if(!TRANSPORT_PACKAGES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="4">No LuST access profiles.</td></tr>';
    return;
  }
  tb.innerHTML = TRANSPORT_PACKAGES.map(function(pkg){
    var service = pkg.preferred_lust_service_id ? lustServiceById(pkg.preferred_lust_service_id) : null;
    var routing = pkg.split_tunnel_enabled ? ('split: ' + ((pkg.split_tunnel_routes_json || []).join(', ') || '-')) : 'full tunnel';
    return '<tr>'
      +'<td class="m">'+esc(pkg.name || '-')+'</td>'
      +'<td>'+esc(service ? service.name : '-')+'</td>'
      +'<td>'+esc(routing)+'</td>'
      +'<td style="display:flex;gap:5px;">'
      +'<button class="btn sm" onclick="showTransportPackage(\''+esc(pkg.id)+'\')">VIEW</button>'
      +'<button class="btn sm" onclick="openTransportPackageModal(\''+esc(pkg.id)+'\')">EDIT</button>'
      +'<button class="btn sm red" onclick="deleteTransportPackageFlow(\''+esc(pkg.id)+'\')">DEL</button>'
      +'</td></tr>';
  }).join('');
};

window.showPlan = function(id){
  var p = planById(id); if(!p) return;
  var profile = p.transport_package_id ? transportPackageById(p.transport_package_id) : null;
  openDP('Subscription ' + p.name, rows([
    ['ID', p.id], ['Name', p.name], ['Billing Mode', p.billing_mode], ['Enabled', p.enabled ? 'yes' : 'no'],
    ['Device Limit', String(p.default_device_limit || '-')], ['Access Profile', profile ? (profile.name || profile.id) : '-'],
    ['Access Schedule', subscriptionAccessSummary(p)], ['Comment', p.comment || '-'], ['Description', p.description || '-']
  ]), { kind:'plan', id:p.id });
};

window.showSubscription = function(id){
  var s = subscriptionById(id); if(!s) return;
  openDP('Subscription', rows([
    ['ID', s.id], ['User', userNameById(s.user_id)], ['Plan', planNameById(s.plan_id)], ['Status', s.status],
    ['Billing Mode', s.billing_mode], ['Expires', s.expires_at ? new Date(s.expires_at).toLocaleString() : 'lifetime'],
    ['Device Limit', String(s.device_limit || '-')], ['Access Window', subscriptionAccessSummary(s)]
  ]), { kind:'subscription', id:s.id });
};

window.showTransportPackage = function(id){
  var pkg = transportPackageById(id); if(!pkg) return;
  var service = pkg.preferred_lust_service_id ? lustServiceById(pkg.preferred_lust_service_id) : null;
  openDP('LuST Access Profile - ' + (pkg.name || pkg.id), rows([
    ['ID', pkg.id], ['Name', pkg.name || '-'], ['LuST Enabled', pkg.lust_enabled ? 'yes' : 'no'],
    ['Preferred Service', service ? service.name : '-'], ['Split Tunnel', pkg.split_tunnel_enabled ? 'enabled' : 'disabled'],
    ['Split Routes', (pkg.split_tunnel_routes_json || []).join(', ') || '-']
  ]) + '<div class="dp-actions"><button class="btn" onclick="openTransportPackageModal(\''+esc(pkg.id)+'\')">EDIT</button><button class="btn red" onclick="deleteTransportPackageFlow(\''+esc(pkg.id)+'\')">DEL</button></div>', { kind:'transport-package', id:pkg.id });
};

window.openPlanModal = function(planId){
  var plan = planId ? planById(planId) : null;
  var tpOptions = [{value:'', label:'вЂ” none вЂ”'}].concat((TRANSPORT_PACKAGES || []).map(function(tp){ return {value:tp.id, label:(tp.name || tp.id)}; }));
  var body = '<form id="planForm"><div class="modal-grid">'
    +formInput('Name', 'name', plan ? plan.name : '', {required:true})
    +(!plan ? formInput('Code (slug)', 'code', '', {required:true}) : '')
    +formSelect('Billing mode', 'billing_mode', plan ? plan.billing_mode : 'periodic', ['manual','lifetime','periodic','trial','fixed_date'])
    +formCheckbox('Enabled', 'enabled', plan ? plan.enabled : true, {caption:'Subscription enabled'})
    +formInput('Duration days', 'duration_days', plan && plan.duration_days != null ? String(plan.duration_days) : '', {type:'number'})
    +formInput('Fixed expires at', 'fixed_expires_at', plan && plan.fixed_expires_at ? plan.fixed_expires_at.slice(0,16) : '', {type:'datetime-local'})
    +formInput('Device limit', 'default_device_limit', plan ? String(plan.default_device_limit || 1) : '1', {type:'number', required:true})
    +formInput('Traffic quota bytes', 'traffic_quota_bytes', plan && plan.traffic_quota_bytes != null ? String(plan.traffic_quota_bytes) : '', {type:'number'})
    +formInput('Speed limit kbps', 'speed_limit_kbps', plan && plan.speed_limit_kbps != null ? String(plan.speed_limit_kbps) : '', {type:'number'})
    +formSelect('Access profile', 'transport_package_id', plan ? (plan.transport_package_id || '') : '', tpOptions)
    +formCheckbox('Restrict access by local time', 'access_window_enabled', !!(plan && plan.access_window_enabled), {caption:'Enable weekly local access window', full:true})
    +formInput('Local start (HH:MM)', 'access_window_start_local', plan ? (plan.access_window_start_local || '') : '', {placeholder:'09:00'})
    +formInput('Local end (HH:MM)', 'access_window_end_local', plan ? (plan.access_window_end_local || '') : '', {placeholder:'18:00'})
    +formTextarea('Comment', 'comment', plan ? (plan.comment || '') : '')
    +'</div></form>';
  openModal(plan ? 'Edit Subscription' : 'New Subscription', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:plan ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('planForm').requestSubmit(); }}
    ]
  });
  bindModalForm('planForm', function(fd){ savePlanForm(fd, planId); });
};

window.openSubscriptionModal = function(subscriptionId){
  var sub = subscriptionId ? subscriptionById(subscriptionId) : null;
  var userOptions = USERS.map(function(u){ return {value:u.id, label:u.username}; });
  var planOptions = [{value:'', label:'-'}].concat(PLANS.map(function(p){ return {value:p.id, label:p.name}; }));
  var body = '<form id="subscriptionForm"><div class="modal-grid">'
    +formSelect('User', 'user_id', sub ? sub.user_id : (USERS[0] ? USERS[0].id : ''), userOptions)
    +formSelect('Plan', 'plan_id', sub ? (sub.plan_id || '') : '', planOptions)
    +formSelect('Status', 'status', sub ? sub.status : 'active', ['pending','active','suspended','expired','revoked'])
    +formSelect('Billing mode', 'billing_mode', sub ? sub.billing_mode : 'manual', ['manual','lifetime','periodic','trial'])
    +formInput('Starts at (ISO)', 'starts_at', sub ? (sub.starts_at || '') : '')
    +formInput('Expires at (ISO)', 'expires_at', sub ? (sub.expires_at || '') : '')
    +formInput('Device limit', 'device_limit', sub ? String(sub.device_limit || 1) : '1', {type:'number'})
    +formInput('Traffic quota bytes', 'traffic_quota_bytes', sub && sub.traffic_quota_bytes != null ? String(sub.traffic_quota_bytes) : '', {type:'number'})
    +formCheckbox('Restrict access by local time', 'access_window_enabled', !!(sub && sub.access_window_enabled), {caption:'Enable weekly local access window', full:true})
    +formInput('Local start (HH:MM)', 'access_window_start_local', sub ? (sub.access_window_start_local || '') : '', {placeholder:'09:00'})
    +formInput('Local end (HH:MM)', 'access_window_end_local', sub ? (sub.access_window_end_local || '') : '', {placeholder:'18:00'})
    +'</div></form>';
  openModal(sub ? 'Edit Subscription' : 'Create Subscription', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:sub ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('subscriptionForm').requestSubmit(); }}
    ]
  });
  bindModalForm('subscriptionForm', function(fd){ saveSubscriptionForm(fd, subscriptionId); });
};

window.openTransportPackageModal = function(pkgId){
  var pkg = pkgId ? transportPackageById(pkgId) : null;
  var lustOptions = [{value:'', label:'вЂ” auto select вЂ”'}].concat((LUST_SERVICES || []).map(function(service){ return {value:service.id, label:service.name}; }));
  var body = '<form id="transportPackageForm"><div class="modal-grid">'
    +formInput('Name', 'name', pkg ? (pkg.name || '') : '', {required:true})
    +formSelect('Preferred LuST service', 'preferred_lust_service_id', pkg ? (pkg.preferred_lust_service_id || '') : '', lustOptions)
    +formCheckbox('Enable LuST', 'lust_enabled', pkg ? !!pkg.lust_enabled : true, {caption:'Issue LuST client profile'})
    +formCheckbox('Enable Split Tunnel', 'split_tunnel_enabled', pkg ? !!pkg.split_tunnel_enabled : false, {caption:'Route only listed CIDRs through LuST'})
    +formTextarea('Split Tunnel Routes', 'split_tunnel_routes', pkg ? (pkg.split_tunnel_routes_json || []).join(', ') : '', {help:'Comma-separated CIDRs'})
    +'</div></form>';
  openModal(pkgId ? 'Edit LuST Access Profile' : 'New LuST Access Profile', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: pkgId ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('transportPackageForm').requestSubmit(); }}
    ]
  });
  bindModalForm('transportPackageForm', function(fd){ saveTransportPackageForm(pkgId, fd); });
};

window.openUserPackageModal = function(userId){
  var pkg = (TRANSPORT_PACKAGES || []).find(function(p){ return p.user_id === userId; }) || null;
  var lustOptions = [{value:'', label:'вЂ” auto select вЂ”'}].concat((LUST_SERVICES || []).map(function(service){ return {value:service.id, label:service.name}; }));
  var body = '<form id="userPkgForm"><div class="modal-grid">'
    +formSelect('Preferred LuST service', 'preferred_lust_service_id', pkg ? (pkg.preferred_lust_service_id || '') : '', lustOptions)
    +formCheckbox('Enable LuST', 'lust_enabled', pkg ? !!pkg.lust_enabled : true, {caption:'Issue LuST profile for this user'})
    +formCheckbox('Split Tunnel', 'split_tunnel_enabled', pkg ? !!pkg.split_tunnel_enabled : false, {caption:'Route only listed CIDRs through LuST'})
    +formInput('GeoIP Country', 'split_tunnel_country_code', pkg ? (pkg.split_tunnel_country_code || '') : '', {help:'ISO 3166-1 alpha-2'})
    +formTextarea('Split Routes', 'split_tunnel_routes', pkg ? (pkg.split_tunnel_routes_json || []).join(', ') : '', {help:'Comma-separated CIDRs'})
    +'</div></form>';
  openModal('User LuST Profile', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Save', className:'btn', onClick:function(){ _userPkgShouldReconcile = false; document.getElementById('userPkgForm').requestSubmit(); }},
      {label:'Save & Reconcile', className:'btn pri', onClick:function(){ _userPkgShouldReconcile = true; document.getElementById('userPkgForm').requestSubmit(); }},
    ]
  });
  bindModalForm('userPkgForm', function(fd){ saveUserPackageForm(userId, fd, _userPkgShouldReconcile); });
};

window.saveTransportPackageForm = async function(pkgId, fd){
  var routes = (fd.get('split_tunnel_routes') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var payload = {
    name: fd.get('name'),
    preferred_lust_service_id: fd.get('preferred_lust_service_id') || null,
    lust_enabled: !!fd.get('lust_enabled'),
    split_tunnel_enabled: !!fd.get('split_tunnel_enabled'),
    split_tunnel_routes: routes,
  };
  try{
    if(pkgId) await apiFetch(API_PREFIX + '/transport-packages/' + encodeURIComponent(pkgId), { method:'PATCH', body:payload });
    else await apiFetch(API_PREFIX + '/transport-packages', { method:'POST', body:payload });
    closeModal();
    await loadTransportPackages();
  }catch(err){ alert(err && err.message ? err.message : String(err)); }
};

window.saveUserPackageForm = async function(userId, fd, reconcile){
  var routes = (fd.get('split_tunnel_routes') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var payload = {
    preferred_lust_service_id: fd.get('preferred_lust_service_id') || null,
    lust_enabled: !!fd.get('lust_enabled'),
    split_tunnel_enabled: !!fd.get('split_tunnel_enabled'),
    split_tunnel_country_code: (fd.get('split_tunnel_country_code') || '').trim().toLowerCase() || null,
    split_tunnel_routes: routes,
  };
  try{
    await apiFetch(API_PREFIX + '/transport-packages/by-user/' + encodeURIComponent(userId), { method:'PUT', body: payload });
    if(reconcile) await apiFetch(API_PREFIX + '/transport-packages/by-user/' + encodeURIComponent(userId) + '/reconcile', { method:'POST' });
    closeModal();
    await loadTransportPackages();
  }catch(err){ alert(err && err.message ? err.message : String(err)); }
};

window.savePlanForm = async function(fd, planId){
  var payload = {
    name: fd.get('name'),
    billing_mode: fd.get('billing_mode'),
    enabled: !!fd.get('enabled'),
    duration_days: fd.get('duration_days') ? parseInt(fd.get('duration_days'), 10) : null,
    fixed_expires_at: fd.get('fixed_expires_at') || null,
    default_device_limit: parseInt(fd.get('default_device_limit'), 10) || 1,
    traffic_quota_bytes: fd.get('traffic_quota_bytes') ? parseInt(fd.get('traffic_quota_bytes'), 10) : null,
    speed_limit_kbps: fd.get('speed_limit_kbps') ? parseInt(fd.get('speed_limit_kbps'), 10) : null,
    transport_package_id: fd.get('transport_package_id') || null,
    access_window_enabled: !!fd.get('access_window_enabled'),
    access_window_start_local: fd.get('access_window_start_local') || null,
    access_window_end_local: fd.get('access_window_end_local') || null,
    comment: fd.get('comment') || null,
  };
  try{
    if(planId){
      await apiFetch(API_PREFIX + '/plans/' + encodeURIComponent(planId), { method:'PATCH', body:payload });
    }else{
      payload.code = (fd.get('code') || '').trim();
      await apiFetch(API_PREFIX + '/plans', { method:'POST', body:payload });
    }
    closeModal();
    await Promise.all([loadPlans(), loadReferralCodes()]);
  }catch(err){ alert(err && err.message ? err.message : String(err)); }
};

window.saveSubscriptionForm = async function(fd, subscriptionId){
  var payload = {
    user_id: fd.get('user_id'),
    plan_id: fd.get('plan_id') || null,
    status: fd.get('status'),
    billing_mode: fd.get('billing_mode'),
    starts_at: fd.get('starts_at') || null,
    expires_at: fd.get('expires_at') || null,
    device_limit: parseInt(fd.get('device_limit'), 10) || 1,
    traffic_quota_bytes: fd.get('traffic_quota_bytes') ? parseInt(fd.get('traffic_quota_bytes'), 10) : null,
    access_window_enabled: !!fd.get('access_window_enabled'),
    access_days_mask: 127,
    access_window_start_local: fd.get('access_window_start_local') || null,
    access_window_end_local: fd.get('access_window_end_local') || null,
  };
  try{
    if(subscriptionId) await apiFetch(API_PREFIX + '/subscriptions/' + encodeURIComponent(subscriptionId), { method:'PATCH', body:payload });
    else await apiFetch(API_PREFIX + '/subscriptions', { method:'POST', body:payload });
    closeModal();
    await loadSubscriptions();
  }catch(err){ alert(err && err.message ? err.message : String(err)); }
};

window.deletePlanFlow = async function(planId){
  if(!confirm('Delete plan?')) return;
  await apiFetch(API_PREFIX + '/plans/' + encodeURIComponent(planId), { method:'DELETE' });
  await Promise.all([loadPlans(), loadSubscriptions(), loadReferralCodes()]);
};

window.deleteSubscriptionFlow = async function(subscriptionId){
  if(!confirm('Delete subscription?')) return;
  await apiFetch(API_PREFIX + '/subscriptions/' + encodeURIComponent(subscriptionId), { method:'DELETE' });
  await loadSubscriptions();
};

window.deleteTransportPackageFlow = async function(pkgId){
  var pkg = transportPackageById(pkgId);
  if(!confirm('Delete access profile ' + (pkg ? (pkg.name || pkgId) : pkgId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/transport-packages/' + encodeURIComponent(pkgId), { method:'DELETE' });
    pushEv('transport_package.deleted', 'access profile deleted: ' + (pkg ? (pkg.name || pkgId) : pkgId));
    closeDP();
    await loadTransportPackages();
  }catch(err){ alert(err && err.message ? err.message : err); }
};

window.assignPoolToPlan = async function(planId){
  var sel = document.getElementById('planPoolAssignSelect');
  var poolId = sel ? sel.value : '';
  if(!poolId) return;
  try{
    await apiFetch(API_PREFIX + '/referral-pools/' + encodeURIComponent(poolId), { method:'PATCH', body:{plan_id: planId} });
    closeModal();
    await Promise.all([loadPlans(), loadReferralCodes()]);
  }catch(err){ alert(err && err.message ? err.message : String(err)); }
};

export {};
