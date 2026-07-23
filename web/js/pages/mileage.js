import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast } from '../api.js';

export async function renderMileage(content) {
  let trips = [];
  let report = null;
  try {
    const res = await apiFetch('/mileage/trips?limit=20');
    const json = await res.json();
    if (json.success) trips = json.data.trips || [];
  } catch (e) { /* API may not support mileage yet */ }

  try {
    const res2 = await apiFetch('/mileage/report');
    const json2 = await res2.json();
    if (json2.success) report = json2.data;
  } catch (e) { /* not available */ }

  const totalMiles = trips.reduce((s, t) => s + t.miles, 0);
  const totalDeduction = trips.reduce((s, t) => s + (t.deduction || 0), 0);

  content.innerHTML = `
    <div class="page-header">
      <h1>🚗 Mileage</h1>
      <p>Track business driving for IRS deductions (${new Date().getFullYear()}: $0.70/mi)</p>
    </div>
    ${report ? `
    <div class="card-row" style="margin-bottom:16px;">
      <div class="stat"><div class="label">Total Miles</div><div class="value blue">${report.total_miles.toFixed(0)}</div></div>
      <div class="stat"><div class="label">Deduction</div><div class="value green">$${fmt(report.total_deduction)}</div></div>
      <div class="stat"><div class="label">Trips</div><div class="value">${report.trip_count}</div></div>
      <div class="stat"><div class="label">Rate</div><div class="value">$${report.rate_per_mile.toFixed(2)}/mi</div></div>
    </div>` : ''}
    <div class="card">
      <h2>Log a Trip</h2>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label style="font-size:0.75rem;color:#888;display:block;">Date</label>
          <input type="date" id="mil-date" value="${new Date().toISOString().slice(0,10)}" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Miles</label>
          <input type="number" id="mil-miles" placeholder="42" style="width:80px;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div style="flex:1;min-width:150px;"><label style="font-size:0.75rem;color:#888;display:block;">Purpose</label>
          <input type="text" id="mil-purpose" placeholder="Client meeting" style="width:100%;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">&nbsp;</label>
          <button class="btn btn-primary" onclick="logMileage()">➕ Log Trip</button></div>
      </div>
      <div id="mil-result" style="margin-top:8px;"></div>
    </div>
    <div class="card">
      <h2>Trip Log ${trips.length > 0 ? `(${trips.length} trips, ${totalMiles.toFixed(0)} mi, $${fmt(totalDeduction)} deduction)` : ''}</h2>
      ${trips.length > 0 ? `
      <table>
        <thead><tr><th>Date</th><th>Purpose</th><th>Miles</th><th class="amount">Deduction</th></tr></thead>
        <tbody>
          ${trips.map(t => `
            <tr>
              <td>${t.date}</td>
              <td>${t.purpose}</td>
              <td>${t.miles.toFixed(1)}</td>
              <td class="amount green">$${fmt(t.deduction)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>` : '<p class="text-muted text-center" style="padding:20px;">No trips logged yet. Use the CLI or API to add trips.</p>'}
    </div>`;
}

window.logMileage = async function() {
  const date = document.getElementById('mil-date').value;
  const miles = parseFloat(document.getElementById('mil-miles').value);
  const purpose = document.getElementById('mil-purpose').value.trim();
  if (!date || !miles || !purpose) {
    document.getElementById('mil-result').innerHTML = '<span style="color:#c92a2a;">Please fill in all fields.</span>';
    return;
  }
  try {
    const res = await apiFetch('/mileage/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, miles, purpose, post_to_ledger: false }),
    });
    const json = await res.json();
    if (json.success) {
      document.getElementById('mil-result').innerHTML =
        `<span style="color:#2b8a3e;">✅ Logged: ${purpose} — ${miles} mi ($${(miles * 0.70).toFixed(2)} deduction)</span>`;
      window.loadPage('mileage');
    } else {
      document.getElementById('mil-result').innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed'}</span>`;
    }
  } catch (err) {
    document.getElementById('mil-result').innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`;
  }
};
