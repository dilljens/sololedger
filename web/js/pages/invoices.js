import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, showConfirm } from '../api.js';

export async function renderNewInvoice(content) {
  content.innerHTML = `
    <div class="page-header">
      <h1>➕ New Invoice</h1>
      <p>Create an invoice for a client</p>
    </div>
    <div class="card">
      <div style="max-width:500px;">
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Client Name</label>
          <input type="text" id="inv-client" placeholder="Acme Corp" style="width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Description</label>
          <textarea id="inv-desc" placeholder="Q3 2026 Consulting Retainer" rows="2" style="width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;resize:vertical;"></textarea>
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Amount ($)</label>
          <input type="number" id="inv-amount" placeholder="5000" step="0.01" style="width:200px;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Client Email (for Stripe payment link)</label>
          <input type="email" id="inv-email" placeholder="client@acme.com" style="width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="createInvoice()" style="padding:12px 24px;">📄 Create Invoice</button>
          <label><input type="checkbox" id="inv-pdf" checked> Generate PDF</label>
          <label><input type="checkbox" id="inv-payment"> Create Stripe payment link</label>
        </div>
        <div id="inv-result" style="margin-top:12px;"></div>
      </div>
    </div>`;
}

window.createInvoice = async function() {
  const client = document.getElementById('inv-client').value.trim();
  const description = document.getElementById('inv-desc').value.trim();
  const amount = parseFloat(document.getElementById('inv-amount').value);
  const email = document.getElementById('inv-email').value.trim();
  const genPdf = document.getElementById('inv-pdf').checked;
  const genPayment = document.getElementById('inv-payment').checked;
  const resultDiv = document.getElementById('inv-result');

  if (!client || !description || !amount) {
    resultDiv.innerHTML = '<span style="color:#c92a2a;">Please fill in client, description, and amount.</span>';
    return;
  }

  resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Creating invoice...</div>';

  try {
    const res = await apiFetch('/invoices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client, description, amount,
        client_email: email || undefined,
        generate_pdf: genPdf,
        payment_link: genPayment,
      }),
    });
    const json = await res.json();
    if (json.success) {
      const d = json.data;
      resultDiv.innerHTML = `
        <div style="background:#d3f9d8;border:1px solid #b2dfdb;border-radius:8px;padding:16px;">
          <strong style="color:#2b8a3e;">✅ Invoice created!</strong>
          <p style="margin-top:8px;">Invoice for ${d.client}: <strong>$${fmt(d.amount)}</strong></p>
          ${d.pdf_url ? `<p><a href="${d.pdf_url}" target="_blank" class="btn btn-outline btn-sm">📄 Download PDF</a></p>` : ''}
          ${d.payment_link ? `<p><a href="${d.payment_link}" target="_blank" class="btn btn-primary btn-sm">💳 Payment Link</a></p>` : ''}
        </div>`;
    } else {
      resultDiv.innerHTML = `<div class="error">⚠ ${escapeHtml(json.error || "") || 'Failed to create invoice'}</div>`;
    }
  } catch (err) {
    resultDiv.innerHTML = `<div class="error">⚠ ${escapeHtml(err.message)}</div>`;
  }
};

export async function renderInvoices(content) {
  const [invData, arData] = await Promise.all([
    apiGet('/invoices'),
    apiGet('/invoices/ar'),
  ]);
  content.innerHTML = `
    <div class="page-header">
      <h1>Invoices</h1>
      <p>Accounts Receivable: ${money(arData.total_ar)}</p>
    </div>
    <div class="card-row" style="margin-bottom:20px;">
      <div class="stat"><div class="label">Outstanding</div><div class="value blue">${money(arData.total_ar)}</div></div>
      <div class="stat"><div class="label">Open Invoices</div><div class="value">${arData.invoice_count}</div></div>
      <div class="stat"><div class="label">Overdue</div><div class="value ${arData.overdue_count > 0 ? 'red' : 'green'}">${arData.overdue_count} (${money(arData.estimated_overdue_amount)})</div></div>
    </div>
    <div class="card">
      <h2>All Invoices</h2>
      ${invData.total === 0 ? '<p class="text-muted text-center" style="padding:20px;">No invoices yet.</p>' : `
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Client</th><th>Description</th><th class="amount">Amount</th><th>Status</th><th></th></tr></thead>
        <tbody>
          ${invData.invoices.map((i, idx) => {
            const invNum = 'INV-' + (i.date ? i.date.slice(0,4) : '2026') + '-' + String(idx+1).padStart(3,'0');
            const paid = i.paid === true;
            return `<tr>
              <td>${i.date}</td>
              <td>${i.client}</td>
              <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${i.description}</td>
              <td class="amount">${money(i.amount)}</td>
              <td>${paid ? '<span class="tag tag-green">Paid</span>' : '<span class="tag tag-red">Unpaid</span>'}</td>
              <td style="display:flex;gap:4px;flex-wrap:wrap;">
                <button class="btn btn-outline btn-sm" onclick="apiDownload('/invoices/${escapeHtml(invNum)}/pdf', '${escapeHtml(invNum)}.pdf')">📄 PDF</button>
                ${!paid ? `<button class="btn btn-success btn-sm" onclick="markInvoicePaid('${escapeHtml(invNum)}', ${i.amount})">✅ Pay</button>` : ''}
                <a href="mailto:?subject=Invoice ${invNum}&body=Hi,%0D%0A%0D%0AInvoice ${invNum} for ${i.description} is attached.%0D%0A%0D%0AAmount due: ${money(i.amount)}%0D%0A%0D%0AThank you!" class="btn btn-outline btn-sm">✉️ Send</a>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`}
    </div>`;
}

window.markInvoicePaid = async function(invNum, amount) {
  const confirmed = await showConfirm('Mark as Paid', `Mark invoice ${invNum} as paid for $${fmt(amount)}?`, { confirmText: 'Mark Paid' });
  if (!confirmed) return;
  try {
    const data = await apiPost(`/invoices/${encodeURIComponent(invNum)}/pay`, {
      amount: amount,
    });
    showToast(`✅ ${data.invoice} marked as paid — $${fmt(data.amount)}`, 'success');
    window.loadPage('invoices');
  } catch (e) {
    showToast('Failed to mark paid: ' + e.message, 'error');
  }
};
