/**
 * BrightLoop Lightweight SVG Charting Engine
 * Pure vanilla JavaScript & SVG data visualizations using real backend context.
 * Zero external libraries or npm dependencies.
 */

class BrightLoopCharts {
  /**
   * Render a sleek donut distribution chart in a container element
   */
  static renderDonut(containerId, data, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0);
    if (total <= 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding:24px;">
          <div class="empty-state-icon" style="font-size:24px;">📊</div>
          <div class="empty-state-text" style="font-size:12px;">No financial metrics recorded yet for chart distribution.</div>
        </div>
      `;
      return;
    }

    const size = options.size || 180;
    const strokeWidth = options.strokeWidth || 22;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    let accumulatedAngle = 0;

    let paths = '';
    data.forEach((item) => {
      const val = Number(item.value || 0);
      if (val <= 0) return;
      const ratio = val / total;
      const strokeDash = ratio * circumference;
      const strokeOffset = circumference - strokeDash;
      const rotation = (accumulatedAngle / total) * 360 - 90;

      paths += `
        <circle cx="${size / 2}" cy="${size / 2}" r="${radius}"
          fill="transparent"
          stroke="${item.color}"
          stroke-width="${strokeWidth}"
          stroke-dasharray="${strokeDash} ${circumference}"
          transform="rotate(${rotation} ${size / 2} ${size / 2})"
          style="transition: stroke-width 0.2s ease, opacity 0.2s ease; cursor: pointer;"
          data-label="${item.label}" data-val="${val}" data-pct="${Math.round(ratio * 100)}"
          onmouseover="this.setAttribute('stroke-width', '${strokeWidth + 4}'); this.style.opacity = '0.9';"
          onmouseout="this.setAttribute('stroke-width', '${strokeWidth}'); this.style.opacity = '1';"
        >
          <title>${item.label}: ₹${val.toLocaleString()} (${Math.round(ratio * 100)}%)</title>
        </circle>
      `;
      accumulatedAngle += val;
    });

    container.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:center; gap:24px; flex-wrap:wrap;">
        <div style="position:relative; width:${size}px; height:${size}px; flex-shrink:0;">
          <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            ${paths}
          </svg>
          <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; pointer-events:none;">
            <span style="font-size:10px; font-weight:750; text-transform:uppercase; color:var(--text-secondary); letter-spacing:0.05em;">Total Pool</span>
            <strong style="font-size:16px; font-weight:800; color:var(--text-primary);">₹${total.toLocaleString()}</strong>
          </div>
        </div>
        <div style="display:flex; flex-direction:column; gap:8px;">
          ${data.map(item => {
            const val = Number(item.value || 0);
            const pct = total > 0 ? Math.round((val / total) * 100) : 0;
            return `
              <div style="display:flex; align-items:center; justify-content:space-between; gap:16px; font-size:12px;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="width:10px; height:10px; border-radius:50%; background-color:${item.color}; display:inline-block;"></span>
                  <span style="font-weight:600; color:var(--text-primary);">${item.label}</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="mono" style="font-weight:700;">₹${val.toLocaleString()}</span>
                  <span class="badge" style="font-size:10px; padding:2px 6px; background:var(--surface-subtle); color:var(--text-secondary);">${pct}%</span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }

  /**
   * Render modern tactile pill bar chart inspired by AETHER reference
   */
  static renderPillBars(containerId, series, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!series || series.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding:24px;">
          <div class="empty-state-text" style="font-size:12px;">No historical billing periods logged yet.</div>
        </div>
      `;
      return;
    }

    const maxVal = Math.max(...series.map(s => Number(s.value || 0)), 1);
    const height = options.height || 140;

    container.innerHTML = `
      <div style="display:flex; align-items:flex-end; justify-content:space-between; gap:12px; height:${height}px; padding:10px 0;">
        ${series.map(item => {
          const val = Number(item.value || 0);
          const barHeight = Math.max(Math.round((val / maxVal) * (height - 30)), 10);
          const color = item.color || '#0E1015';
          return `
            <div style="flex:1; display:flex; flex-direction:column; align-items:center; gap:8px; height:100%; justify-content:flex-end;">
              <span class="mono" style="font-size:10px; font-weight:700; color:var(--text-secondary);">₹${val}</span>
              <div style="width:100%; max-width:38px; height:${barHeight}px; background-color:${color}; border-radius:var(--radius-pill); transition:transform 0.2s cubic-bezier(0.16,1,0.3,1), opacity 0.2s;"
                onmouseover="this.style.transform = 'scaleY(1.05)'; this.style.opacity = '0.85';"
                onmouseout="this.style.transform = 'scaleY(1)'; this.style.opacity = '1';"
                title="${item.label}: ₹${val}">
              </div>
              <span style="font-size:11px; font-weight:600; color:var(--text-secondary); text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:60px;">
                ${item.label}
              </span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }
}

window.BrightLoopCharts = BrightLoopCharts;

