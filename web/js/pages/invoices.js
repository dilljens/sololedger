import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, showConfirm } from '../api.js';

const escAttr = (s) => escapeHtml(s).replace(/"/g, '&quot;');

export async function renderNewInvoice(content) {
  content.innerHTML = `
    <div class="page-header">
      <h1>➕ New Invoice</h1>
      <p>Create an invoice for a client</p>
    </div>
    <div class="card">
      <div style="max-width:500px;">
        <div style="margin-bottom:16px;">
          <label class="text-body">Client Name</label>
          <input type="text" id="inv-client" placeholder="Acme Corp" class="border">
        </div>
        <div style="margin-bottom:16px;">
          <label class="text-body">Description</label>
          <textarea id="inv-desc" placeholder="Q3 2026 Consulting Retainer" rows="2" class="border"></textarea>
        </div>
        <div style="margin-bottom:16px;">
          <label class="text-body">Amount ($)</label>
          <input type="number" id="inv-amount" placeholder="5000" step="0.01" class="border">
        </div>
        <div style="margin-bottom:16px;">
          <label class="text-body">Client Email (for Stripe payment link)</label>
          <input type="email" id="inv-email" placeholder="client@acme.com" class="border">
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
    resultDiv.innerHTML = '<span class="text-error">Please fill in client, description, and amount.</span>';
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
        <div class="bg-success">
          <strong class="text-success">✅ Invoice created!</strong>
          <p style="margin-top:8px;">Invoice for ${escapeHtml(d.client)}: <strong>$${fmt(d.amount)}</strong></p>
          ${d.pdf_url ? `<p><a href="${escAttr(d.pdf_url)}" target="_blank" class="btn btn-outline btn-sm">📄 Download PDF</a></p>` : ''}
          ${d.payment_link ? `<p><a href="${escAttr(d.payment_link)}" target="_blank" class="btn btn-primary btn-sm">💳 Payment Link</a></p>` : ''}
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
          ${(invData.invoices || []).map((i, idx) => {
            const invNum = 'INV-' + ((i.date || '').slice(0,4) || '2026') + '-' + String(idx+1).padStart(3,'0');
            const paid = i.paid === true;
            return `<tr>
              <td>${escapeHtml(i.date)}</td>
              <td>${escapeHtml(i.client)}</td>
              <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(i.description)}</td>
              <td class="amount">${money(i.amount)}</td>
              <td>${paid ? '<span class="tag tag-green">Paid</span>' : '<span class="tag tag-red">Unpaid</span>'}</td>
              <td style="display:flex;gap:4px;flex-wrap:wrap;">
                <button class="btn btn-outline btn-sm" onclick="apiDownload('/invoices/${escapeHtml(invNum)}/pdf', '${escapeHtml(invNum)}.pdf')">📄 PDF</button>
                ${!paid ? `<button class="btn btn-success btn-sm" onclick="markInvoicePaid('${escapeHtml(invNum)}', ${i.amount})">✅ Pay</button>` : ''}
                <a href="mailto:?subject=Invoice ${escAttr(invNum)}&body=Hi,%0D%0A%0D%0AInvoice ${escAttr(invNum)} for ${escAttr(i.description)} is attached.%0D%0A%0D%0AAmount due: ${money(i.amount)}%0D%0A%0D%0AThank you!" class="btn btn-outline btn-sm">✉️ Send</a>
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
