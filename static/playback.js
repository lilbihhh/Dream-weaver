(function () {
  var frame = document.getElementById("playback-frame");
  var scene = document.getElementById("dreamscape");
  var media = document.getElementById("dream-media");
  var playBtn = document.getElementById("play-btn");
  var pauseBtn = document.getElementById("pause-btn");
  if (!scene) { return; }

  function markMediaReady() {
    if (frame) { frame.classList.add("media-ready"); }
  }

  if (media) {
    if (media.tagName === "VIDEO") {
      if (media.readyState >= 2) {
        markMediaReady();
      } else {
        media.addEventListener("canplay", markMediaReady, { once: true });
      }
    } else if (media.complete) {
      markMediaReady();
    } else {
      media.addEventListener("load", markMediaReady, { once: true });
    }
  }

  if (playBtn) {
    playBtn.addEventListener("click", function () {
      scene.classList.remove("paused");
      if (frame) { frame.classList.remove("paused"); }
      if (media && media.tagName === "VIDEO") {
        var playback = media.play();
        if (playback) { playback.catch(function () {}); }
      }
    });
  }
  if (pauseBtn) {
    pauseBtn.addEventListener("click", function () {
      scene.classList.add("paused");
      if (frame) { frame.classList.add("paused"); }
      if (media && media.tagName === "VIDEO") { media.pause(); }
    });
  }
})();
