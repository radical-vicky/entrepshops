/* =========================================================================
   Lightbox — full-screen image viewer for product galleries.
   - Click any [data-lightbox] element to open.
   - Pinch to zoom (mobile), scroll to zoom (desktop), drag to pan.
   - Double-tap / double-click toggles between 1x and 2.5x.
   - Left/Right arrows (keyboard + on-screen) and horizontal swipe
     switch between images in the same gallery.
   - Share button uses the Web Share API on mobile, falls back to
     copy-image-URL on desktop.
   - Save button triggers a browser download of the original file.
   - Esc or click on the backdrop to close.
   ========================================================================= */
(function () {
    'use strict';

    const ZOOM_MIN = 1;
    const ZOOM_MAX = 5;
    const ZOOM_STEP = 0.4;
    const DOUBLE_TAP_ZOOM = 2.5;

    let overlay = null;
    let stage = null;
    let imgEl = null;
    let captionEl = null;
    let counterEl = null;
    let images = [];
    let index = 0;
    let scale = 1;
    let tx = 0;
    let ty = 0;
    let dragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragStartTx = 0;
    let dragStartTy = 0;
    let lastTapTime = 0;
    let lastTapX = 0;
    let lastTapY = 0;
    let swipeStartX = null;
    let swipeStartY = null;

    function build() {
        if (overlay) return;

        overlay = document.createElement('div');
        overlay.className = 'lightbox';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Image viewer');
        overlay.innerHTML = `
            <div class="lightbox-backdrop"></div>
            <div class="lightbox-stage">
                <img class="lightbox-image" alt="">
            </div>
            <div class="lightbox-caption"></div>
            <div class="lightbox-counter"></div>
            <div class="lightbox-toolbar">
                <button type="button" class="lightbox-btn" data-action="zoom-out" aria-label="Zoom out">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="8" y1="11" x2="14" y2="11"/><line x1="20" y1="20" x2="16.65" y2="16.65"/></svg>
                </button>
                <button type="button" class="lightbox-btn" data-action="zoom-in" aria-label="Zoom in">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="8" y1="11" x2="14" y2="11"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="20" y1="20" x2="16.65" y2="16.65"/></svg>
                </button>
                <button type="button" class="lightbox-btn" data-action="reset" aria-label="Reset zoom">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 10 9 10"/></svg>
                </button>
                <button type="button" class="lightbox-btn" data-action="share" aria-label="Share">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="10.5" x2="15.4" y2="6.5"/><line x1="8.6" y1="13.5" x2="15.4" y2="17.5"/></svg>
                </button>
                <button type="button" class="lightbox-btn" data-action="download" aria-label="Save image">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </button>
                <button type="button" class="lightbox-btn" data-action="close" aria-label="Close">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <button type="button" class="lightbox-nav lightbox-prev" data-action="prev" aria-label="Previous image">
                <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <button type="button" class="lightbox-nav lightbox-next" data-action="next" aria-label="Next image">
                <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
        `;
        document.body.appendChild(overlay);

        stage = overlay.querySelector('.lightbox-stage');
        imgEl = overlay.querySelector('.lightbox-image');
        captionEl = overlay.querySelector('.lightbox-caption');
        counterEl = overlay.querySelector('.lightbox-counter');

        overlay.addEventListener('click', onClick);
        imgEl.addEventListener('load', () => { captionEl.textContent = imgEl.alt || ''; });
        imgEl.addEventListener('wheel', onWheel, { passive: false });
        imgEl.addEventListener('dblclick', onDoubleClick);

        // Pointer events (mouse + touch + pen).
        imgEl.addEventListener('pointerdown', onPointerDown);
        overlay.addEventListener('pointermove', onPointerMove);
        overlay.addEventListener('pointerup', onPointerUp);
        overlay.addEventListener('pointercancel', onPointerUp);

        document.addEventListener('keydown', onKey);
    }

    function open(imgs, startIndex) {
        build();
        images = imgs;
        index = startIndex || 0;
        overlay.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        show();
    }

    function close() {
        if (!overlay) return;
        overlay.classList.remove('is-open');
        document.body.style.overflow = '';
        resetZoom();
    }

    function show() {
        const item = images[index];
        if (!item) return;
        resetZoom();
        imgEl.src = item.src;
        imgEl.alt = item.alt || '';
        captionEl.textContent = item.alt || '';
        counterEl.textContent = images.length > 1 ? `${index + 1} / ${images.length}` : '';
        overlay.classList.toggle('has-multiple', images.length > 1);
    }

    function next() { if (images.length > 1) { index = (index + 1) % images.length; show(); } }
    function prev() { if (images.length > 1) { index = (index - 1 + images.length) % images.length; show(); } }

    function resetZoom() {
        scale = 1; tx = 0; ty = 0;
        applyTransform();
    }

    function applyTransform() {
        imgEl.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
        imgEl.style.cursor = scale > 1 ? 'grab' : 'zoom-in';
        overlay.classList.toggle('is-zoomed', scale > 1);
    }

    function zoomAt(factor, originX, originY) {
        const newScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, scale * factor));
        if (newScale === scale) return;
        // Keep the point under the cursor roughly fixed.
        const rect = imgEl.getBoundingClientRect();
        const cx = originX - (rect.left + rect.width / 2);
        const cy = originY - (rect.top + rect.height / 2);
        const ratio = newScale / scale;
        tx = tx * ratio - cx * (ratio - 1);
        ty = ty * ratio - cy * (ratio - 1);
        scale = newScale;
        if (scale === 1) { tx = 0; ty = 0; }
        applyTransform();
    }

    function onClick(e) {
        const action = e.target.closest('[data-action]');
        if (action) {
            e.stopPropagation();
            const a = action.dataset.action;
            if (a === 'close') close();
            else if (a === 'next') next();
            else if (a === 'prev') prev();
            else if (a === 'zoom-in') zoomAt(1 + ZOOM_STEP, e.clientX, e.clientY);
            else if (a === 'zoom-out') zoomAt(1 / (1 + ZOOM_STEP), e.clientX, e.clientY);
            else if (a === 'reset') resetZoom();
            else if (a === 'share') share();
            else if (a === 'download') download();
            return;
        }
        // Click on the backdrop (not on the image) closes.
        if (e.target.classList.contains('lightbox-backdrop')) close();
    }

    function onWheel(e) {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1 + ZOOM_STEP / 2 : 1 / (1 + ZOOM_STEP / 2);
        zoomAt(factor, e.clientX, e.clientY);
    }

    function onDoubleClick(e) {
        e.preventDefault();
        if (scale > 1) {
            resetZoom();
        } else {
            zoomAt(DOUBLE_TAP_ZOOM, e.clientX, e.clientY);
        }
    }

    function onPointerDown(e) {
        // Long-press is fine; we only drag when zoomed.
        if (scale <= 1) return;
        dragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        dragStartTx = tx;
        dragStartTy = ty;
        imgEl.setPointerCapture(e.pointerId);
        imgEl.style.cursor = 'grabbing';
    }

    function onPointerMove(e) {
        if (dragging) {
            tx = dragStartTx + (e.clientX - dragStartX);
            ty = dragStartTy + (e.clientY - dragStartY);
            applyTransform();
            return;
        }
        // Detect swipe to change image — only when not zoomed.
        if (scale > 1) return;
        if (swipeStartX === null) { swipeStartX = e.clientX; swipeStartY = e.clientY; return; }
    }

    function onPointerUp(e) {
        if (dragging) {
            dragging = false;
            imgEl.style.cursor = scale > 1 ? 'grab' : 'zoom-in';
            return;
        }
        if (scale > 1 || swipeStartX === null) { swipeStartX = null; swipeStartY = null; return; }
        const dx = e.clientX - swipeStartX;
        const dy = e.clientY - swipeStartY;
        swipeStartX = null; swipeStartY = null;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
            if (dx < 0) next(); else prev();
        }
    }

    function onKey(e) {
        if (!overlay || !overlay.classList.contains('is-open')) return;
        if (e.key === 'Escape') close();
        else if (e.key === 'ArrowRight') next();
        else if (e.key === 'ArrowLeft') prev();
        else if (e.key === '+' || e.key === '=') zoomAt(1 + ZOOM_STEP, window.innerWidth / 2, window.innerHeight / 2);
        else if (e.key === '-') zoomAt(1 / (1 + ZOOM_STEP), window.innerWidth / 2, window.innerHeight / 2);
    }

    async function share() {
        const item = images[index];
        if (!item) return;
        const shareData = {
            title: document.title,
            text: item.alt || '',
            url: item.src,
        };
        if (navigator.share && navigator.canShare && navigator.canShare(shareData)) {
            try { await navigator.share(shareData); } catch (e) { /* user cancelled */ }
            return;
        }
        // Desktop fallback — copy the URL to clipboard.
        try {
            await navigator.clipboard.writeText(item.src);
            flashCaption('Image link copied to clipboard');
        } catch (e) {
            flashCaption('Press Ctrl/Cmd+C to copy the link');
        }
    }

    function download() {
        const item = images[index];
        if (!item) return;
        const a = document.createElement('a');
        a.href = item.src;
        a.download = (item.alt || 'image').slice(0, 60).replace(/[^\w\-]+/g, '-') + '.jpg';
        a.rel = 'noopener';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    let flashTimer;
    function flashCaption(msg) {
        if (!captionEl) return;
        const original = captionEl.textContent;
        captionEl.textContent = msg;
        clearTimeout(flashTimer);
        flashTimer = setTimeout(() => { captionEl.textContent = original; }, 2200);
    }

    // Expose for product_detail.html.
    window.Lightbox = { open };
})();
