/* =========================================================================
   API-driven product grid.
   Fetches /api/v1/products/ and renders cards client-side.
   Falls back to the server-rendered grid (already in the DOM) if the
   API is unavailable for any reason.
   ========================================================================= */
(function () {
    const grid = document.getElementById('product-grid');
    if (!grid) return;

    const API = '/api/v1/products/';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function cardHTML(p) {
        const img = p.image
            ? `<img src="${esc(p.image)}" alt="${esc(p.name)}">`
            : `<div class="img-placeholder"><svg viewBox="0 0 24 24" style="color:#45D68A"><use href="#icon-bottle"/></svg></div>`;

        const price = p.price_range[0] === p.price_range[1]
            ? `KES ${esc(p.price_range[0])}`
            : `KES ${esc(p.price_range[0])}–${esc(p.price_range[1])}`;

        const stock = p.in_stock
            ? `<p class="badge badge-success in-stock-badge">In stock</p>
               <form action="/store/cart/add/${p.id}/" method="post" class="ajax-add-form">
                 <input type="hidden" name="quantity" value="1">
                 <input type="hidden" name="next" value="${esc(window.location.pathname)}">
                 <button type="submit" class="btn btn-small">Add to cart</button>
               </form>`
            : `<p class="badge badge-muted">Out of stock</p>`;

        return `
            <article class="product-card">
                <a href="/store/product/${esc(p.slug)}/">
                    ${img}
                    <h4>${esc(p.name)}</h4>
                </a>
                <p class="price">${price}</p>
                ${stock}
            </article>
        `;
    }

    async function loadProducts(params, push) {
        const url = API + '?' + new URLSearchParams(params).toString();
        grid.classList.add('is-loading');
        try {
            const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
            if (!res.ok) throw new Error('API error');
            const data = await res.json();
            grid.innerHTML = data.results.map(cardHTML).join('') ||
                `<p class="product-grid-empty">No products found.</p>`;
            if (push) {
                const qs = new URLSearchParams(params).toString();
                history.pushState({}, '', qs ? `?${qs}#shop` : '#shop');
            }
        } catch (e) {
            // Leave the server-rendered grid in place.
            console.warn('Grid API fetch failed, keeping server-rendered grid.', e);
        } finally {
            grid.classList.remove('is-loading');
        }
    }

    window.GridAPI = { loadProducts };
})();
