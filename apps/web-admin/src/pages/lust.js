window.refreshLustServices = async function refreshLustServices(){
  window.LUST_SERVICES = await apiFetch(API_PREFIX + '/lust-services');
  window.renderLustServices();
};

window.renderLustServices = function renderLustServices(){
  var tb = document.getElementById('lusttb');
  if(!tb) return;
  if(!window.LUST_SERVICES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="8">No LuST services.</td></tr>';
    return;
  }
  tb.innerHTML = window.LUST_SERVICES.map(function(service){
    return '<tr onclick="showLustService(\''+esc(service.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(service.name)+'</td>'
      +'<td>'+esc(service.node_name || nById(service.node_id).name || service.node_id)+'</td>'
      +'<td>'+esc(service.public_host || '-')+'</td>'
      +'<td>'+esc(String(service.public_port || service.listen_port || '-'))+'</td>'
      +'<td>'+esc(service.h2_path || '-')+'</td>'
      +'<td>'+esc(String(service.peer_count || 0))+'</td>'
      +'<td>'+sp(service.state || 'planned')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();openLustServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();applyLustServiceFlow(\''+esc(service.id)+'\')">APPLY</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteLustServiceFlow(\''+esc(service.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.showLustService = function showLustService(id){
  var service = lustServiceById(id); if(!service) return;
  openDP('LuST ' + service.name, rows([
    ['ID', service.id],
    ['Name', service.name],
    ['Node', service.node_name || nById(service.node_id).name || service.node_id],
    ['Public Host', service.public_host],
    ['Public Port', String(service.public_port || service.listen_port || '-')],
    ['Listen', (service.listen_host || '0.0.0.0') + ':' + String(service.listen_port || '-')],
    ['TLS SNI', service.tls_server_name || service.public_host || '-'],
    ['ACME E-mail', service.acme_email || '-'],
    ['HTTP/2 Path', service.h2_path || '-'],
    ['Auth', service.auth_scheme || '-'],
    ['DNS', service.client_dns_resolver || '-'],
    ['Peers', String(service.peer_count || 0)],
    ['State', service.state || '-'],
    ['Description', service.description || '-']
  ])
  +'<div class="dp-actions">'
    +'<button class="btn" onclick="openLustServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
    +'<button class="btn" onclick="applyLustServiceFlow(\''+esc(service.id)+'\')">APPLY</button>'
    +'<button class="btn red" onclick="deleteLustServiceFlow(\''+esc(service.id)+'\')">DELETE</button>'
  +'</div>', { kind:'lust-service', id:service.id });
};

window.openLustServiceModal = function openLustServiceModal(serviceId){
  var service = serviceId ? lustServiceById(serviceId) : null;
  var nodeOptions = (NODES || []).map(function(node){ return { value: node.id, label: node.name }; });
  var body = '<form id="lustServiceForm"><div class="modal-grid">'
    +formInput('Name', 'name', service ? service.name : '', {required:true})
    +formSelect('Node', 'node_id', service ? service.node_id : (NODES[0] ? NODES[0].id : ''), nodeOptions, {help:'Managed node that terminates LuST.'})
    +formInput('Listen host', 'listen_host', service ? (service.listen_host || '0.0.0.0') : '0.0.0.0', {required:true})
    +formInput('Listen port', 'listen_port', service ? String(service.listen_port || 443) : '443', {required:true, type:'number'})
    +formInput('Public host', 'public_host', service ? (service.public_host || '') : '', {required:true})
    +formInput('Public port', 'public_port', service && service.public_port != null ? String(service.public_port) : '', {type:'number'})
    +formInput('TLS server name', 'tls_server_name', service ? (service.tls_server_name || '') : '', {help:'Defaults to public host when empty.'})
    +formInput('ACME e-mail', 'acme_email', service ? (service.acme_email || '') : '', {help:"Optional Let's Encrypt account e-mail. When empty, certbot runs without e-mail."})
    +formInput('HTTP/2 path', 'h2_path', service ? (service.h2_path || '/lust') : '/lust', {required:true})
    +formInput('DNS resolver', 'client_dns_resolver', service ? (service.client_dns_resolver || '') : '', {help:'Optional client-side DNS hint.'})
    +formTextarea('Description', 'description', service ? (service.description || '') : '')
    +'</div></form>';
  openModal(service ? 'Edit LuST Service' : 'New LuST Service', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:service ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('lustServiceForm').requestSubmit(); }}
    ]
  });
  bindModalForm('lustServiceForm', function(fd){ saveLustServiceForm(fd, serviceId); });
};

window.saveLustServiceForm = async function saveLustServiceForm(fd, serviceId){
  var payload = {
    name: fd.get('name'),
    node_id: fd.get('node_id'),
    listen_host: fd.get('listen_host'),
    listen_port: parseInt(fd.get('listen_port'), 10) || 443,
    public_host: fd.get('public_host'),
    public_port: fd.get('public_port') ? parseInt(fd.get('public_port'), 10) : null,
    tls_server_name: (fd.get('tls_server_name') || '').trim() || null,
    acme_email: (fd.get('acme_email') || '').trim() || null,
    h2_path: fd.get('h2_path'),
    client_dns_resolver: (fd.get('client_dns_resolver') || '').trim() || null,
    description: (fd.get('description') || '').trim() || null,
  };
  try{
    if(serviceId){
      await apiFetch(API_PREFIX + '/lust-services/' + encodeURIComponent(serviceId), { method:'PATCH', body:payload });
    }else{
      await apiFetch(API_PREFIX + '/lust-services', { method:'POST', body:payload });
    }
    closeModal();
    await refreshLustServices();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.deleteLustServiceFlow = async function deleteLustServiceFlow(serviceId){
  var service = lustServiceById(serviceId);
  if(!confirm('Delete LuST service ' + (service ? service.name : serviceId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/lust-services/' + encodeURIComponent(serviceId), { method:'DELETE' });
    closeDP();
    await refreshLustServices();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.applyLustServiceFlow = async function applyLustServiceFlow(serviceId){
  try{
    await apiFetch(API_PREFIX + '/lust-services/' + encodeURIComponent(serviceId) + '/apply', { method:'POST', body:{} });
    await refreshLustServices();
    await loadPeers?.();
    var service = lustServiceById(serviceId);
    if(service) window.showLustService(serviceId);
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

export {};
