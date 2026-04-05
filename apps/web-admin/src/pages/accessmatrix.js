var ACCESS_MATRIX = [];
var ACCESS_MATRIX_GROUPS = [
  'access_rules',
  'audit_logs',
  'maintenance',
  'system_summary',
  'fail2ban',
  'worker_health',
  'realtime',
  'jobs',
  'nodes',
  'node_traffic',
  'devices',
  'users',
  'lust_services',
  'transport_packages',
  'plans',
  'subscriptions',
  'quick_deploy',
  'referral_codes',
  'registrations',
  'peers',
  'route_policies',
  'transit_policies',
  'dns_policies',
  'geo_policies',
  'probes',
  'peer_traffic',
  'topology',
  'support',
  'client_updates',
];
var ACCESS_ROLE_ORDER = ['l1', 'l2', 'l3', 'audit', 'admin'];

function _accessGroupName(prefix) {
  return String(prefix || '').replace(/_/g, ' ').replace(/\b\w/g, function(ch){ return ch.toUpperCase(); });
}

function _accessGroupedItems(items) {
  var grouped = {};
  (items || []).forEach(function(item) {
    var prefix = String((item.permission_key || '').split('.')[0] || 'other');
    if (!grouped[prefix]) grouped[prefix] = [];
    grouped[prefix].push(item);
  });
  return grouped;
}

function _accessRoleCheckbox(item, role) {
  var checked = (item.allowed_roles || []).indexOf(role) >= 0 ? ' checked' : '';
  return '<label style="display:inline-flex;align-items:center;gap:4px;font-size:12px;">'
    + '<input type="checkbox" data-role="' + esc(role) + '"' + checked + '>'
    + '<span>' + esc(role.toUpperCase()) + '</span>'
    + '</label>';
}

function _renderAccessMatrix() {
  var root = document.getElementById('accessMatrixContent');
  if (!root) return;
  if (!ACCESS_MATRIX.length) {
    root.innerHTML = '<div class="empty-state">No access rules available.</div>';
    return;
  }

  var grouped = _accessGroupedItems(ACCESS_MATRIX);
  var order = ACCESS_ROLE_ORDER.slice();
  var groupOrder = ACCESS_MATRIX_GROUPS.filter(function(prefix) { return !!grouped[prefix]; })
    .concat(Object.keys(grouped).filter(function(prefix) { return ACCESS_MATRIX_GROUPS.indexOf(prefix) < 0; }).sort());

  root.innerHTML = groupOrder.map(function(prefix) {
    var rows = (grouped[prefix] || []).slice().sort(function(a, b) {
      return String(a.permission_key || '').localeCompare(String(b.permission_key || ''));
    }).map(function(item) {
      return '<tr data-permission-key="' + esc(item.permission_key) + '">'
        + '<td class="m">' + esc(item.permission_key) + '</td>'
        + '<td>' + esc(item.description || '-') + '</td>'
        + '<td><label style="display:inline-flex;align-items:center;gap:6px;"><input type="checkbox" data-enabled="1"' + (item.enabled ? ' checked' : '') + '><span>' + (item.enabled ? 'enabled' : 'disabled') + '</span></label></td>'
        + '<td><div style="display:flex;gap:10px;flex-wrap:wrap;">' + order.map(function(role) { return _accessRoleCheckbox(item, role); }).join('') + '</div></td>'
        + '<td>' + esc(item.source || 'default') + '</td>'
        + '<td style="white-space:nowrap;display:flex;gap:6px;">'
        + '<button class="btn sm" onclick="saveAccessRule(\'' + esc(item.permission_key) + '\')">SAVE</button>'
        + (item.source === 'db' ? '<button class="btn sm red" onclick="resetAccessRule(\'' + esc(item.permission_key) + '\')">RESET</button>' : '')
        + '</td>'
        + '</tr>';
    }).join('');
    return '<div style="margin-bottom:18px;">'
      + '<div class="stitle">' + esc(_accessGroupName(prefix)) + '</div>'
      + '<div class="tw"><table>'
      + '<thead><tr><th>Permission</th><th>Description</th><th>Enabled</th><th>Allowed Roles</th><th>Source</th><th>Actions</th></tr></thead>'
      + '<tbody>' + rows + '</tbody>'
      + '</table></div>'
      + '</div>';
  }).join('');
}

window.loadAccessMatrix = async function loadAccessMatrix() {
  var root = document.getElementById('accessMatrixContent');
  if (root) root.innerHTML = '<div style="color:var(--t2);padding:12px;">Loading…</div>';
  var payload = await apiFetch(API_PREFIX + '/access-rules/matrix');
  ACCESS_MATRIX = Array.isArray(payload && payload.items) ? payload.items : [];
  _renderAccessMatrix();
};

window.saveAccessRule = async function saveAccessRule(permissionKey) {
  var row = document.querySelector('tr[data-permission-key="' + permissionKey.replace(/"/g, '\\"') + '"]');
  if (!row) return;
  var enabledEl = row.querySelector('input[data-enabled="1"]');
  var allowedRoles = [];
  row.querySelectorAll('input[data-role]').forEach(function(input) {
    if (input.checked) allowedRoles.push(String(input.getAttribute('data-role') || '').trim().toLowerCase());
  });
  if (!allowedRoles.length) {
    alert('At least one role must remain enabled.');
    return;
  }
  var item = ACCESS_MATRIX.find(function(entry) { return entry.permission_key === permissionKey; }) || {};
  var body = {
    description: item.description || '',
    allowed_roles: allowedRoles,
    enabled: !!(enabledEl && enabledEl.checked),
  };
  await apiFetch(API_PREFIX + '/access-rules/' + encodeURIComponent(permissionKey), { method: 'PUT', body: body });
  await window.loadAccessMatrix();
};

window.resetAccessRule = async function resetAccessRule(permissionKey) {
  if (!confirm('Reset this permission to the default rule set?')) return;
  await apiFetch(API_PREFIX + '/access-rules/' + encodeURIComponent(permissionKey), { method: 'DELETE' });
  await window.loadAccessMatrix();
};

export {};
