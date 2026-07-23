/**
 * Temba Digital Bridge — Shared About Modal
 * Injects the About modal into any page. Call openAboutModal() from any link.
 */
(function () {
  const html = `
  <div id="temba-about-modal" style="
    position:fixed;inset:0;background:rgba(10,37,64,0.5);z-index:6000;
    display:flex;align-items:center;justify-content:center;padding:1rem;
    backdrop-filter:blur(4px);opacity:0;pointer-events:none;
    transition:opacity 0.25s;
  ">
    <div style="
      background:#fff;border-radius:24px;
      box-shadow:0 8px 40px rgba(10,37,64,0.14);
      width:100%;max-width:560px;max-height:90vh;overflow-y:auto;
      transform:translateY(20px) scale(0.97);
      transition:transform 0.3s cubic-bezier(0.34,1.56,0.64,1);
    " id="temba-about-box">
      <!-- Header -->
      <div style="padding:1.5rem 1.75rem 1rem;border-bottom:1px solid #E2E8F0;display:flex;align-items:center;justify-content:space-between;">
        <h2 style="font-size:18px;font-weight:800;color:#0A2540;font-family:'Plus Jakarta Sans',sans-serif;display:flex;align-items:center;gap:8px;">
          <span style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#1565C0,#29B6F6);display:inline-flex;align-items:center;justify-content:center;">
            <i class="ti ti-droplet" style="color:#fff;font-size:15px;"></i>
          </span>
          About Temba Digital Bridge
        </h2>
        <button onclick="closeAboutModal()" style="background:none;border:none;font-size:20px;color:#94A3B8;cursor:pointer;padding:4px;border-radius:6px;" title="Close">
          <i class="ti ti-x"></i>
        </button>
      </div>
      <!-- Body -->
      <div style="padding:1.5rem 1.75rem;font-family:'Plus Jakarta Sans',sans-serif;">
        <p style="font-size:14.5px;color:#475569;line-height:1.75;margin-bottom:1.25rem;">
          Temba Digital Bridge is a <strong style="color:#0A2540;">civic platform</strong> built to close the communication gap between Rwandan communities and the water service providers that serve them.
        </p>
        <p style="font-size:14px;color:#475569;line-height:1.7;margin-bottom:1.5rem;">
          Accessible via <strong>web app</strong> or <strong>USSD (*384*36640#)</strong> on any phone — no smartphone or internet required. Available in <strong>English</strong> and <strong>Kinyarwanda</strong>.
        </p>
        <div style="margin-bottom:1.5rem;">
          <div style="font-size:11px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Registered Providers</div>
          <div id="about-provider-pills">
            ${['WASAC','Water Access Rwanda','IRIBA Water Group','Aquasan Limited','Pro Water Rwanda','Temba Digital Bridge'].map(p =>
              `<span style="display:inline-flex;align-items:center;gap:6px;background:#F0FAFF;border:1px solid #B3E5FC;border-radius:20px;padding:5px 14px;font-size:12.5px;font-weight:600;color:#1565C0;margin:3px;">
                <i class="ti ti-building"></i> ${p}
              </span>`).join('')}
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:1.5rem;">
          ${[['6+','Water Service Providers'],['5','Administrative Levels'],['2','Languages Supported'],['Web + USSD','Access Channels']].map(([num,lbl]) =>
            `<div style="text-align:center;background:#F0FAFF;border-radius:12px;padding:1.25rem;">
              <div style="font-size:26px;font-weight:800;color:#1565C0;font-family:'Plus Jakarta Sans',sans-serif;">${num}</div>
              <div style="font-size:12px;color:#475569;font-weight:600;margin-top:4px;">${lbl}</div>
            </div>`).join('')}
        </div>
        <div style="background:#F0F4F8;border-radius:10px;padding:12px 16px;font-size:13px;color:#475569;line-height:1.6;">
          <strong style="color:#0A2540;">Our Mission:</strong> Enable every Rwandan — whether online or on a basic phone — to report water issues, request services, and communicate transparently with providers.
        </div>
      </div>
      <!-- Footer -->
      <div style="padding:1rem 1.75rem 1.5rem;border-top:1px solid #E2E8F0;display:flex;justify-content:flex-end;">
        <button onclick="closeAboutModal()" style="
          background:linear-gradient(135deg,#1565C0,#29B6F6);color:#fff;border:none;
          border-radius:10px;font-family:'Plus Jakarta Sans',sans-serif;
          font-size:14px;font-weight:600;padding:10px 24px;cursor:pointer;
        ">Close</button>
      </div>
    </div>
  </div>`;

  document.body.insertAdjacentHTML('beforeend', html);

  window.openAboutModal = function () {
    const m = document.getElementById('temba-about-modal');
    const b = document.getElementById('temba-about-box');
    // Refresh provider pills from live API data if available
    const pills = document.getElementById('about-provider-pills');
    if (pills && window._apiProviders && window._apiProviders.length) {
      pills.innerHTML = window._apiProviders.map(p =>
        `<span style="display:inline-flex;align-items:center;gap:6px;background:#F0FAFF;border:1px solid #B3E5FC;border-radius:20px;padding:5px 14px;font-size:12.5px;font-weight:600;color:#1565C0;margin:3px;">
          <i class="ti ti-building"></i> ${p.organization_name}
        </span>`).join('');
    }
    m.style.pointerEvents = 'all';
    m.style.opacity = '1';
    b.style.transform = 'none';
  };

  window.closeAboutModal = function () {
    const m = document.getElementById('temba-about-modal');
    const b = document.getElementById('temba-about-box');
    m.style.opacity = '0';
    m.style.pointerEvents = 'none';
    b.style.transform = 'translateY(20px) scale(0.97)';
  };

  document.addEventListener('keydown', e => { if (e.key === 'Escape') window.closeAboutModal && closeAboutModal(); });
  document.getElementById('temba-about-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('temba-about-modal')) closeAboutModal();
  });
}());
