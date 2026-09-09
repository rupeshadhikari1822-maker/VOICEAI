// Scroll-scrubbed background film: draws one of the pre-rendered frames of the
// CloudFRM logo zoom-in onto a fixed full-viewport canvas, picking the frame
// from how far down the page has been scrolled (first frame at the top, last
// frame at the bottom).
//
// The source video is only 1280x720, so the canvas is intentionally rendered
// at 1 CSS pixel per device pixel (not devicePixelRatio) -- doubling or
// tripling the backbuffer for a "retina" canvas can't add detail that isn't
// in the source, it only forces a bigger upscale of a blurrier image and
// costs more to composite on every scroll frame.
(function () {
  const FRAME_COUNT = 122;
  const FRAME_URL = (n) => `/static/landing/media/scrollframes/frame_${String(n).padStart(4, "0")}.webp`;
  const MAX_CONCURRENT_LOADS = 6;

  const canvas = document.getElementById("scrollFilmCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  const images = new Array(FRAME_COUNT);
  let currentFrame = 0;
  let renderedFrame = -1;
  let dpr = 1;

  function resizeCanvas() {
    // Match the screen's real device pixels, or the canvas itself gets
    // blurred by the browser scaling it up to fit a HiDPI/scaled display --
    // same reason a plain <img> with no retina variant looks soft.
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(window.innerWidth * dpr);
    canvas.height = Math.round(window.innerHeight * dpr);
    renderedFrame = -1;
  }

  function nearestLoadedFrame(index) {
    if (images[index]) return images[index];
    for (let d = 1; d < FRAME_COUNT; d++) {
      const before = index - d;
      const after = index + d;
      if (before >= 0 && images[before]) return images[before];
      if (after < FRAME_COUNT && images[after]) return images[after];
    }
    return null;
  }

  // Displayed well below the source's 1280px width, so this is always a
  // downscale -- guaranteed crisp, never the blur that comes from stretching
  // a 720p source up to fill a much bigger box.
  const MAX_WIDTH_CSS = 640;

  function drawFrame(index) {
    const img = nearestLoadedFrame(index);
    if (!img) return;
    const cw = canvas.width;
    const ch = canvas.height;
    const cssWidth = Math.min(MAX_WIDTH_CSS, window.innerWidth * 0.92);
    const cssHeight = cssWidth * (img.naturalHeight / img.naturalWidth);
    const dw = cssWidth * dpr;
    const dh = cssHeight * dpr;
    const dx = (cw - dw) / 2;
    const dy = (ch - dh) / 2;

    ctx.clearRect(0, 0, cw, ch);
    ctx.globalCompositeOperation = "source-over";
    ctx.drawImage(img, dx, dy, dw, dh);

    // The video's "black" background isn't pure #000, so even with the
    // screen blend mode above, a faint rectangle would still show where it
    // meets the page background. Fading the edges to true transparency
    // (rather than relying on the colors matching) removes the seam
    // entirely, so only the glowing linework reads as visible.
    ctx.globalCompositeOperation = "destination-in";
    const cx = dx + dw / 2;
    const cy = dy + dh / 2;
    const gradient = ctx.createRadialGradient(cx, cy, Math.min(dw, dh) * 0.1, cx, cy, Math.max(dw, dh) * 0.58);
    gradient.addColorStop(0, "rgba(0,0,0,1)");
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, cw, ch);
    ctx.globalCompositeOperation = "source-over";
  }

  function frameForScroll() {
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const fraction = scrollable > 0 ? window.scrollY / scrollable : 0;
    const clamped = Math.min(1, Math.max(0, fraction));
    return Math.min(FRAME_COUNT - 1, Math.floor(clamped * FRAME_COUNT));
  }

  let ticking = false;
  function onScroll() {
    currentFrame = frameForScroll();
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      if (renderedFrame !== currentFrame) {
        drawFrame(currentFrame);
        renderedFrame = currentFrame;
      }
      ticking = false;
    });
  }

  // Loads frames in order with limited concurrency, so 120-odd requests
  // don't all hit the network/decoder at once and stall the scroll thread.
  function loadFrames() {
    let nextIndex = 0;
    let inFlight = 0;

    function loadOne(index) {
      inFlight++;
      const img = new Image();
      img.decoding = "async";
      const done = () => {
        inFlight--;
        pump();
      };
      img.onload = () => {
        images[index] = img;
        if (renderedFrame === -1 || index === currentFrame) {
          drawFrame(currentFrame);
          renderedFrame = currentFrame;
        }
        done();
      };
      img.onerror = done;
      img.src = FRAME_URL(index + 1);
    }

    function pump() {
      while (inFlight < MAX_CONCURRENT_LOADS && nextIndex < FRAME_COUNT) {
        loadOne(nextIndex++);
      }
    }

    pump();
  }

  resizeCanvas();
  currentFrame = frameForScroll();

  window.addEventListener("resize", () => {
    resizeCanvas();
    drawFrame(currentFrame);
  });
  window.addEventListener("scroll", onScroll, { passive: true });

  loadFrames();
})();
