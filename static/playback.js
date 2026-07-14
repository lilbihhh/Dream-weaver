(function () {
  var scene = document.getElementById("dreamscape");
  var playBtn = document.getElementById("play-btn");
  var pauseBtn = document.getElementById("pause-btn");
  if (!scene) { return; }
  if (playBtn) { playBtn.addEventListener("click", function () { scene.classList.remove("paused"); }); }
  if (pauseBtn) { pauseBtn.addEventListener("click", function () { scene.classList.add("paused"); }); }
})();
