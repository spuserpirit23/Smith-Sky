(function () {
  const config = window.SmithSkyCafe || {};
  const apiBase = (config.apiBaseUrl || '').replace(/\/$/, '');
  const money = (minor, currency) =>
    new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'INR' }).format((minor || 0) / 100);

  function request(path, options = {}) {
    return fetch(apiBase + path, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    }).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || 'Request failed');
      }
      return data;
    });
  }

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (key === 'class') node.className = value;
      else if (key === 'html') node.innerHTML = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    });
    [].concat(children).forEach((child) => {
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return node;
  }

  function setApp(app, children) {
    app.innerHTML = '';
    [].concat(children).forEach((child) => app.appendChild(child));
  }

  function poll(app, renderer) {
    if (app.sscPoller) clearInterval(app.sscPoller);
    app.sscPoller = setInterval(() => {
      if (document.visibilityState === 'visible') {
        renderer(app);
      }
    }, 8000);
  }

  function alert(message, type = '') {
    return el('div', { class: `ssc-alert ${type}` }, [message]);
  }

  function topbar(title, subtitle, actions = []) {
    return el('div', { class: 'ssc-topbar' }, [
      el('div', {}, [el('h1', { class: 'ssc-title' }, [title]), el('div', { class: 'ssc-subtitle' }, [subtitle])]),
      el('div', { class: 'ssc-actions' }, actions),
    ]);
  }

  function logoutButton() {
    return el('button', {
      class: 'ssc-button ghost',
      onclick: () => request('/api/v1/auth/logout', { method: 'POST', body: '{}' }).finally(() => {
        window.location.href = config.loginUrl || '/cafe-login/';
      }),
    }, ['Logout']);
  }

  async function renderLogin(app) {
    const form = el('form', { class: 'ssc-form' }, [
      el('h1', { class: 'ssc-title' }, ['SMITH & SKY']),
      el('p', { class: 'ssc-muted' }, ['Cafe inventory and sales dashboard']),
      el('label', {}, ['Email', el('input', { class: 'ssc-input', name: 'email', type: 'email', autocomplete: 'username', required: 'required' })]),
      el('label', {}, ['Password', el('input', { class: 'ssc-input', name: 'password', type: 'password', autocomplete: 'current-password', required: 'required' })]),
      el('button', { class: 'ssc-button', type: 'submit' }, ['Login']),
    ]);
    const message = el('div');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      message.innerHTML = '';
      const body = JSON.stringify(Object.fromEntries(new FormData(form)));
      try {
        const data = await request('/api/v1/auth/login', { method: 'POST', body });
        window.location.href = data.user.role === 'admin' ? (config.adminUrl || '/cafe-admin/') : (config.portalUrl || '/cafe-portal/');
      } catch (error) {
        message.appendChild(alert(error.message, 'error'));
      }
    });
    setApp(app, [form, message]);
  }

  async function renderAdmin(app) {
    try {
      const [me, cafes, stock, report] = await Promise.all([
        request('/api/v1/me'),
        request('/api/v1/admin/cafes'),
        request('/api/v1/admin/stock'),
        request('/api/v1/admin/reports/sales'),
      ]);
      const totalStock = stock.stock.reduce((sum, row) => sum + Number(row.available_stock || 0), 0);
      const lowStock = stock.stock.filter((row) => Number(row.available_stock) <= Number(row.low_stock_threshold)).length;
      const salesValue = report.sales.reduce((sum, row) => sum + Number(row.sales_value_minor || 0), 0);
      setApp(app, [
        topbar('Admin Dashboard', `Signed in as ${me.user.full_name}`, [logoutButton()]),
        el('div', { class: 'ssc-grid' }, [
          kpi('Cafes', cafes.cafes.length),
          kpi('Total stock', totalStock),
          kpi('Low stock', lowStock),
          kpi('Sales value', money(salesValue, 'INR')),
        ]),
        sectionTable('Stock by cafe', ['Cafe', 'Product', 'Available', 'Threshold'], stock.stock.map((row) => [
          row.cafe_name, row.product_name, row.available_stock, row.low_stock_threshold,
        ])),
        el('div', { class: 'ssc-actions' }, [
          el('a', { class: 'ssc-button secondary', href: '/cafe-admin/cafes/' }, ['Manage cafes']),
          el('a', { class: 'ssc-button secondary', href: '/cafe-admin/deliveries/' }, ['Deliveries']),
          el('a', { class: 'ssc-button secondary', href: '/cafe-admin/reports/' }, ['Reports']),
        ]),
      ]);
      poll(app, renderAdmin);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  async function renderCafes(app) {
    try {
      const cafes = await request('/api/v1/admin/cafes');
      const message = el('div');
      const form = el('form', { class: 'ssc-form' }, [
        el('h3', {}, ['Create cafe']),
        el('label', {}, ['Name', el('input', { class: 'ssc-input', name: 'name', required: 'required' })]),
        el('label', {}, ['Address', el('input', { class: 'ssc-input', name: 'address' })]),
        el('button', { class: 'ssc-button', type: 'submit' }, ['Create cafe']),
      ]);
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        message.innerHTML = '';
        try {
          await request('/api/v1/admin/cafes', {
            method: 'POST',
            body: JSON.stringify(Object.fromEntries(new FormData(form))),
          });
          message.appendChild(alert('Cafe created.'));
          renderCafes(app);
        } catch (error) {
          message.appendChild(alert(error.message, 'error'));
        }
      });
      setApp(app, [
        topbar('Cafes', 'Create and review cafe locations', [logoutButton()]),
        form,
        message,
        sectionTable('Cafe list', ['Name', 'Address', 'Status', 'Stock'], cafes.cafes.map((row) => [
          row.name, row.address || '', row.status, row.total_stock,
        ])),
      ]);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  async function renderDeliveries(app) {
    try {
      const [cafes, products] = await Promise.all([request('/api/v1/admin/cafes'), request('/api/v1/products')]);
      const lines = el('div');
      const cafeSelect = select('cafe_id', cafes.cafes.map((c) => [c.id, c.name]));
      const message = el('div');
      const addLine = () => lines.appendChild(line(products.products));
      addLine();
      const form = el('form', { class: 'ssc-form' }, [
        el('h3', {}, ['Record delivery']),
        el('label', {}, ['Cafe', cafeSelect]),
        el('label', {}, ['Reference', el('input', { class: 'ssc-input', name: 'reference' })]),
        lines,
        el('div', { class: 'ssc-actions' }, [
          el('button', { class: 'ssc-button ghost', type: 'button', onclick: addLine }, ['Add line']),
          el('button', { class: 'ssc-button', type: 'submit' }, ['Submit delivery']),
        ]),
      ]);
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        message.innerHTML = '';
        try {
          await request('/api/v1/admin/deliveries', {
            method: 'POST',
            body: JSON.stringify({
              cafe_id: cafeSelect.value,
              reference: form.reference.value,
              items: collectItems(lines),
            }),
          });
          message.appendChild(alert('Delivery recorded.'));
          lines.innerHTML = '';
          addLine();
        } catch (error) {
          message.appendChild(alert(error.message, 'error'));
        }
      });
      setApp(app, [topbar('Deliveries', 'Post stock received by each cafe', [logoutButton()]), form, message]);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  async function renderReports(app) {
    try {
      const report = await request('/api/v1/admin/reports/sales');
      const rows = report.sales.map((row) => [
        row.cafe_name,
        row.product_name,
        row.units_sold,
        money(row.sales_value_minor, row.currency),
      ]);
      setApp(app, [
        topbar('Reports', 'Sales totals by cafe and product', [logoutButton()]),
        sectionTable('Sales report', ['Cafe', 'Product', 'Units sold', 'Value'], rows),
      ]);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  async function renderPortal(app) {
    try {
      const [me, stock] = await Promise.all([request('/api/v1/me'), request('/api/v1/cafe/stock')]);
      const totalStock = stock.stock.reduce((sum, row) => sum + Number(row.available_stock || 0), 0);
      const lowStock = stock.stock.filter((row) => Number(row.available_stock) <= Number(row.low_stock_threshold)).length;
      setApp(app, [
        topbar(stock.cafe.name, `Signed in as ${me.user.full_name}`, [logoutButton()]),
        el('div', { class: 'ssc-actions' }, [
          el('a', { class: 'ssc-button', href: '/cafe-portal/new-sale/' }, ['New sale']),
          el('a', { class: 'ssc-button secondary', href: '/cafe-portal/history/' }, ['History']),
        ]),
        el('div', { class: 'ssc-grid' }, [kpi('Available units', totalStock), kpi('Low-stock items', lowStock)]),
        sectionTable('Available stock', ['Product', 'SKU', 'Available', 'Price'], stock.stock.map((row) => [
          row.product_name, row.sku || '', row.available_stock, money(row.unit_price_minor, row.currency),
        ])),
      ]);
      poll(app, renderPortal);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  async function renderNewSale(app) {
    try {
      const stock = await request('/api/v1/cafe/stock');
      const lines = el('div');
      const message = el('div');
      const addLine = () => lines.appendChild(line(stock.stock.map((p) => ({ id: p.product_id, name: `${p.product_name} (${p.available_stock} available)` }))));
      addLine();
      const form = el('form', { class: 'ssc-form' }, [
        el('h3', {}, ['New sale']),
        lines,
        el('div', { class: 'ssc-actions' }, [
          el('button', { class: 'ssc-button ghost', type: 'button', onclick: addLine }, ['Add line']),
          el('button', { class: 'ssc-button', type: 'submit' }, ['Submit sale']),
        ]),
      ]);
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        message.innerHTML = '';
        try {
          await request('/api/v1/cafe/sales', {
            method: 'POST',
            body: JSON.stringify({ idempotency_key: crypto.randomUUID(), items: collectItems(lines) }),
          });
          message.appendChild(alert('Sale recorded.'));
          lines.innerHTML = '';
          addLine();
        } catch (error) {
          message.appendChild(alert(error.message, 'error'));
        }
      });
      setApp(app, [topbar('New Sale', stock.cafe.name, [logoutButton()]), form, message]);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  async function renderHistory(app) {
    try {
      const sales = await request('/api/v1/cafe/sales');
      setApp(app, [
        topbar('Transaction History', 'Latest cafe sales', [logoutButton()]),
        sectionTable('Sales', ['Reference', 'Sold at', 'Items', 'Total'], sales.sales.map((row) => [
          row.transaction_ref, new Date(row.sold_at).toLocaleString(), row.item_count, money(row.total_minor, row.currency),
        ])),
      ]);
    } catch (error) {
      showAuthError(app, error);
    }
  }

  function kpi(label, value) {
    return el('div', { class: 'ssc-card' }, [el('h3', {}, [label]), el('div', { class: 'ssc-kpi' }, [String(value)])]);
  }

  function sectionTable(title, headers, rows) {
    const table = el('table', { class: 'ssc-table' }, [
      el('thead', {}, [el('tr', {}, headers.map((h) => el('th', {}, [h])))]),
      el('tbody', {}, rows.length ? rows.map((row) => el('tr', {}, row.map((cell) => el('td', {}, [String(cell ?? '')])))) : [
        el('tr', {}, [el('td', { colspan: headers.length }, ['No records yet.'])]),
      ]),
    ]);
    return el('div', { class: 'ssc-card' }, [el('h3', {}, [title]), el('div', { class: 'ssc-table-wrap' }, [table])]);
  }

  function select(name, options) {
    return el('select', { class: 'ssc-select', name }, options.map(([value, label]) => el('option', { value }, [label])));
  }

  function line(products) {
    return el('div', { class: 'ssc-line' }, [
      select('product_id', products.map((p) => [p.id || p.product_id, p.name || p.product_name])),
      el('input', { class: 'ssc-input', name: 'quantity', type: 'number', min: '1', value: '1' }),
      el('button', { class: 'ssc-button ghost', type: 'button', onclick: (event) => event.currentTarget.closest('.ssc-line').remove() }, ['Remove']),
    ]);
  }

  function collectItems(lines) {
    return Array.from(lines.querySelectorAll('.ssc-line')).map((row) => ({
      product_id: row.querySelector('[name="product_id"]').value,
      quantity: row.querySelector('[name="quantity"]').value,
    }));
  }

  function showAuthError(app, error) {
    setApp(app, [
      alert(error.message, 'error'),
      el('a', { class: 'ssc-button', href: config.loginUrl || '/cafe-login/' }, ['Go to login']),
    ]);
  }

  const renderers = {
    login: renderLogin,
    admin: renderAdmin,
    cafes: renderCafes,
    deliveries: renderDeliveries,
    reports: renderReports,
    portal: renderPortal,
    'new-sale': renderNewSale,
    history: renderHistory,
  };

  function boot() {
    document.querySelectorAll('[data-ssc-view]').forEach((app) => {
      const view = app.getAttribute('data-ssc-view');
      const render = renderers[view];
      if (render) render(app);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
