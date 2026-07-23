import { apiFetch, escapeHtml, showToast, fmt } from '../api.js';

export async function renderReceipts(content) {
  content.innerHTML = `
      <div class="page-header">
        <h1>🧾 Receipts</h1>
        <p>All receipt documents attached to your ledger</p>
      </div>
      <div class="card" id="receipt-list">
        <div class="loading"><div class="spinner"></div>Loading receipts...</div>
      </div>
      <div class="card">
        <h2>📸 New Receipt</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Take a photo or upload a PDF receipt. It will be scanned,
          categorized, and permanently attached to your ledger.
        </p>
        <a href="#" onclick="loadPage('capture')" class="btn btn-primary">📸 Capture Receipt</a>
      </div>`;

  try {
    const res = await apiFetch('/receipts/list');
    const json = await res.json();
    const docs = json.success ? json.data.documents || [] : [];

    const listDiv = document.getElementById('receipt-list');
    if (docs.length === 0) {
      listDiv.innerHTML = '<p class="text-muted text-center" style="padding:20px;">No receipt documents attached yet.</p>';
    } else {
      listDiv.innerHTML = `
        <h2>Attached Receipts (${docs.length})</h2>
        <table>
          <thead><tr><th>Date</th><th>Account</th><th>File</th></tr></thead>
          <tbody>
            ${docs.map(d => `
              <tr>
                <td>${d.date}</td>
                <td><span class="tag tag-blue">${d.account}</span></td>
                <td><code style="font-size:0.75rem;">${d.path.split('/').pop()}</code></td>
              </tr>
            `).join('')}
          </tbody>
        </table>`;
    }
  } catch (err) {
    document.getElementById('receipt-list').innerHTML =
      '<div class="error">⚠ Could not load receipts: ' + escapeHtml(err.message) + '</div>';
  }
}

export function renderCaptureContent(content) {
  content.innerHTML = `
    <div class="page-header">
      <h1>📸 Capture Receipt</h1>
      <p>Snap a receipt photo with your camera or upload one from your gallery</p>
    </div>
    <div class="card">
      <h2>1. Choose Receipt</h2>
      <div class="text-center" style="padding:30px;">
        <label class="btn btn-primary" style="font-size:1rem;padding:14px 28px;cursor:pointer;display:inline-flex;align-items:center;gap:8px;">
          📷 Take Photo or Upload
          <input type="file" id="receipt-file" accept="image/*,application/pdf" capture="environment" style="display:none;" onchange="handleReceiptUpload(this)">
        </label>
        <p class="text-muted text-sm mt-3">Supports JPG, PNG, PDF receipts</p>
      </div>
    </div>
    <div id="receipt-result" style="display:none;">
      <div class="card">
        <h2>2. Review &amp; Confirm</h2>
        <div id="receipt-preview"></div>
      </div>
      <div class="card" id="receipt-match-section" style="display:none;">
        <h2>🔗 Matching Bank Transaction</h2>
        <div id="receipt-matches"></div>
      </div>
      <div class="card">
        <h2>3. Category</h2>
        <div id="receipt-category"></div>
        <div style="margin-top:12px;display:flex;gap:8px;" id="receipt-actions">
          <button class="btn btn-primary" onclick="confirmReceipt()">✅ Append to Ledger</button>
          <button class="btn btn-outline" onclick="resetCapture()">🔄 Reset</button>
        </div>
      </div>
    </div>
    <div id="receipt-done" style="display:none;">
      <div class="card" class="text-center" style="padding:30px;">
        <h2 style="font-size:1.5rem;">✅ Receipt Recorded</h2>
        <p style="color:#666;margin:8px 0;" id="receipt-done-detail"></p>
        <button class="btn btn-outline" onclick="resetCapture()">📸 Capture Another</button>
      </div>
    </div>`;
}

window.renderCaptureContent = function() {
  const content = document.getElementById('page-content');
  renderCaptureContent(content);
};

window._receiptBusy = false;

window.handleReceiptUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  if (window._receiptBusy) {
    showToast('Already processing a receipt, please wait...', 'warning');
    input.value = '';
    return;
  }
  window._receiptBusy = true;

  const resultDiv = document.getElementById('receipt-result');
  const previewDiv = document.getElementById('receipt-preview');
  const matchSection = document.getElementById('receipt-match-section');
  const matchesDiv = document.getElementById('receipt-matches');
  const categoryDiv = document.getElementById('receipt-category');
  const doneDiv = document.getElementById('receipt-done');
  const doneDetail = document.getElementById('receipt-done-detail');

  resultDiv.style.display = 'none';
  matchSection.style.display = 'none';
  doneDiv.style.display = 'none';

  previewDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Scanning receipt...</div>';
  resultDiv.style.display = 'block';

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');
    const res = await apiFetch('/receipts/scan', { method: 'POST', body: formData });
    const json = await res.json();
    if (!json.success) throw new Error(escapeHtml(escapeHtml(json.error)) || 'Scan failed');
    const data = json.data;

    previewDiv.innerHTML = `
      <table>
        <tr><td style="width:120px;"><strong>Merchant</strong></td><td>${data.merchant || 'Unknown'}</td></tr>
        <tr><td><strong>Date</strong></td><td>${data.date || 'Unknown'}</td></tr>
        <tr><td><strong>Total</strong></td><td><strong>$${fmt(data.total || 0)}</strong></td></tr>
        ${data.line_items && data.line_items.length ? `
        <tr><td><strong>Items</strong></td><td>${data.line_items.slice(0,5).map(i => `<span style="display:block;">· ${i.description}: $${fmt(i.amount)}</span>`).join('')}${data.line_items.length > 5 ? `<span style="color:#888;">...and ${data.line_items.length-5} more</span>` : ''}</td></tr>
        ` : ''}
      </table>
      <p class="text-muted text-sm mt-3">${file.name} (${(file.size/1024).toFixed(0)} KB)</p>`;

    let suggestedAccount = '';
    if (data.merchant) {
      const catRes = await apiFetch('/categories/suggest?merchant=' + encodeURIComponent(data.merchant));
      const catJson = await catRes.json();
      if (catJson.success && catJson.data && catJson.data.account) {
        suggestedAccount = catJson.data.account;
        const conf = catJson.data.confidence;
        const confLabel = conf === 'high' ? '✅' : conf === 'medium' ? '⚠️' : '❓';
        categoryDiv.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span>${confLabel} Suggested: <strong>${suggestedAccount}</strong></span>
            <input type="text" id="receipt-account" value="${suggestedAccount}" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.85rem;width:250px;">
            <button class="btn btn-outline btn-sm" onclick="learnCategory()">✓ Learn</button>
          </div>`;
      } else {
        categoryDiv.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span>Category:</span>
            <input type="text" id="receipt-account" value="Expenses:Miscellaneous" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.85rem;width:250px;">
          </div>`;
      }
    } else {
      categoryDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <span>Category:</span>
          <input type="text" id="receipt-account" value="Expenses:Miscellaneous" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.85rem;width:250px;">
        </div>`;
    }

    const total = data.total || 0;
    if (total > 0) {
      const matchRes = await apiFetch('/receipts/match?amount=' + total + '&merchant=' + encodeURIComponent(data.merchant || ''));
      const matchJson = await matchRes.json();
      if (matchJson.success && matchJson.data && matchJson.data.matches && matchJson.data.matches.length > 0) {
        matchSection.style.display = 'block';
        matchesDiv.innerHTML = matchJson.data.matches.slice(0,3).map(m => `
          <label style="display:flex;align-items:center;gap:10px;padding:8px;border:1px solid #ddd;border-radius:6px;margin:4px 0;cursor:pointer;">
            <input type="radio" name="receipt-match" value='${JSON.stringify(m).replace(/'/g, "&#39;")}'>
            <span>${m.date} — <strong>${m.description}</strong> — $${fmt(m.amount)}</span>
            <span class="tag ${m.match_score > 0.95 ? 'tag-green' : 'tag-blue'}">${(m.match_score * 100).toFixed(0)}% match</span>
          </label>
        `).join('');
      }
    }

    window._receiptData = data;
    window._receiptFile = file;
    window._receiptBusy = false;
  } catch (err) {
    previewDiv.innerHTML = '<div class="error">⚠ ' + escapeHtml(err.message) + '</div>';
    window._receiptBusy = false;
  }
};

window.confirmReceipt = async function() {
  const data = window._receiptData;
  const file = window._receiptFile;
  if (!data || !data.total) { alert('No receipt data to save.'); return; }
  const account = document.getElementById('receipt-account')?.value || 'Expenses:Miscellaneous';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'false');
    formData.append('account', account);
    const res = await apiFetch('/receipts/scan', { method: 'POST', body: formData });
    const json = await res.json();
    if (!json.success) throw new Error(escapeHtml(json.error) || 'Failed');
    document.getElementById('receipt-result').style.display = 'none';
    document.getElementById('receipt-done').style.display = 'block';
    document.getElementById('receipt-done-detail').textContent = `${data.merchant || 'Receipt'} — $${fmt(data.total)} → ${account}`;
    if (data.merchant) {
      await apiFetch('/categories/learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant: data.merchant, account, correct: true }),
      });
    }
    window._receiptBusy = false;
  } catch (err) { alert('❌ Error: ' + escapeHtml(err.message)); window._receiptBusy = false; }
};

window.learnCategory = async function() {
  const receiptData = window._receiptData;
  const receiptAccount = document.getElementById('receipt-account')?.value;
  if (receiptData && receiptData.merchant && receiptAccount) {
    await apiFetch('/categories/learn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant: receiptData.merchant, account: receiptAccount, correct: true }),
    });
    alert('✅ Category learned for ' + receiptData.merchant);
    return;
  }

  const account = document.getElementById('cat-correct')?.value || '';
  const merchant = document.getElementById('cat-merchant')?.value || '';
  if (!merchant || !account) return;
  try {
    await apiFetch('/categories/learn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, account, correct: true }),
    });
    document.getElementById('cat-suggestion').innerHTML =
      '<p style="color:#2b8a3e;">✅ Learned: ' + escapeHtml(merchant) + ' → ' + escapeHtml(account) + '</p>';
  } catch (err) {
    alert('❌ Error: ' + escapeHtml(err.message));
  }
};

window.resetCapture = function() {
  window._receiptData = null;
  window._receiptFile = null;
  const active = document.querySelector('[data-page].active');
  if (active) window.loadPage(active.dataset.page);
};
