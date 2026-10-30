// The home and Publications pages: the topic filters over the publication list, the slideshow, and clips that play
// only while on screen.
// Without this script every topic shows and the filters jump to their headings.
(function () {
  "use strict";

  var chips = Array.prototype.slice.call(document.querySelectorAll(".filters .chip"));
  var groups = Array.prototype.slice.call(document.querySelectorAll(".topic[data-topic]"));
  chips.forEach(function (chip) {
    chip.setAttribute("role", "button");
    chip.setAttribute("aria-pressed", chip.classList.contains("on") ? "true" : "false");
    chip.addEventListener("click", function (event) {
      event.preventDefault();
      var topic = chip.getAttribute("data-topic");
      chips.forEach(function (other) {
        var on = other === chip;
        other.classList.toggle("on", on);
        other.setAttribute("aria-pressed", on ? "true" : "false");
      });
      groups.forEach(function (group) {
        if (topic === "all" || group.getAttribute("data-topic") === topic) {
          group.removeAttribute("data-off");
        } else {
          group.setAttribute("data-off", "");
        }
      });
    });
    chip.addEventListener("keydown", function (event) {
      if (event.key === " ") {  // a button answers Space as well as Enter
        event.preventDefault();
        chip.click();
      }
    });
  });

  // On a phone the bio shows four lines until "Read more" (home.css); elsewhere the button stays hidden.
  var more = document.querySelector(".bio-more");
  if (more) {
    more.addEventListener("click", function () {
      var open = document.getElementById("bio").classList.toggle("open");
      more.setAttribute("aria-expanded", open ? "true" : "false");
      more.textContent = open ? "Show less" : "Read more";
    });
  }

  function play(video) {
    var playing = video.play();
    if (playing && playing.catch) {
      playing.catch(function () {});
    }
  }

  // Research highlights (Tianyu: like hyunwooyuk.com's "camera roll"): one captioned slide at a time, moving on
  // after DWELL, or once its clip has played through if that takes longer. Picking a tab shows that slide and the
  // roll goes on from it; Pause stops the roll and the clip. Only the shown slide's clip plays, and nothing moves
  // while the slideshow is off screen or the tab is hidden. Like the clips, it moves even when the system asks for
  // reduced motion (Windows asks for it whenever its animation effects are off). Without scripts every slide shows
  // and the tabs jump to them.
  var DWELL = 9000;  // ms a slide shows, at least
  var box = document.querySelector(".highlights");
  if (box) {
    var slides = Array.prototype.slice.call(box.querySelectorAll(".slide"));
    var tabs = Array.prototype.slice.call(box.querySelectorAll(".hl-tab"));
    var pause = box.querySelector(".hl-pause");
    var at = 0;
    var paused = false;
    var onScreen = true;
    var timer = null;

    var clip = function (i) {
      return slides[i].querySelector("video");
    };
    var visible = function () {
      return onScreen && !document.hidden;
    };

    // A clip plays once it can: playing earlier hides its poster and leaves the slide blank. canplay also comes
    // after a rewind, which loadeddata (once per clip) does not.
    var start = function (video) {
      if (video.readyState >= 3) {
        play(video);
        return;
      }
      video.preload = "auto";
      video.addEventListener("canplay", function () {
        if (video === clip(at) && !paused && visible()) {
          play(video);
        }
      }, { once: true });
    };

    var schedule = function () {
      window.clearTimeout(timer);
      if (paused || !visible()) {
        return;
      }
      var video = clip(at);
      var length = video && isFinite(video.duration) ? video.duration * 1000 : 0;
      timer = window.setTimeout(function () {
        show((at + 1) % slides.length);
      }, Math.max(DWELL, length));
    };

    var show = function (i) {
      var old = clip(at);
      if (old && i !== at) {
        old.pause();
      }
      slides.forEach(function (slide, k) {
        slide.classList.toggle("on", k === i);
      });
      tabs.forEach(function (tab, k) {
        if (k === i) {
          tab.setAttribute("aria-current", "true");
        } else {
          tab.removeAttribute("aria-current");
        }
      });
      at = i;
      var video = clip(i);
      if (video && !paused && visible()) {
        if (video.readyState >= 1) {
          video.currentTime = 0;
        }
        start(video);
      }
      var next = clip((i + 1) % slides.length);
      if (next) {
        next.preload = "auto";  // so its first frame is ready by its turn
      }
      schedule();
    };

    var setPaused = function (value) {
      paused = value;
      pause.textContent = value ? "Play" : "Pause";
      pause.setAttribute("aria-pressed", value ? "true" : "false");
      var video = clip(at);
      if (video) {
        if (value) {
          video.pause();
        } else if (visible()) {
          start(video);
        }
      }
      schedule();
    };

    var resume = function () {
      var video = clip(at);
      if (video) {
        if (!paused && visible()) {
          start(video);
        } else {
          video.pause();
        }
      }
      schedule();
    };

    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function (event) {
        event.preventDefault();
        show(i);
      });
    });
    pause.addEventListener("click", function () {
      setPaused(!paused);
    });
    document.addEventListener("visibilitychange", resume);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (items) {
        onScreen = items[items.length - 1].isIntersecting;
        resume();
      }).observe(box);
    }
    show(0);
  }

  // The other clips play while on screen, even when the system asks for reduced motion: they are the page's
  // evidence, and Windows asks for it whenever its animation effects are switched off.
  var videos = Array.prototype.slice.call(document.querySelectorAll("video")).filter(function (video) {
    return !video.closest(".highlights");  // the slideshow plays its own
  });
  if (!("IntersectionObserver" in window)) {
    return;
  }
  // They load only as they near the screen (not all at once), and play once they can: playing earlier would blank
  // their posters.
  var watcher = new IntersectionObserver(function (items) {
    items.forEach(function (item) {
      var video = item.target;
      video.near = item.isIntersecting;
      if (!video.near) {
        video.pause();
      } else if (video.readyState >= 3) {
        play(video);
      } else {
        video.preload = "auto";
        video.addEventListener("canplay", function () {
          if (video.near) {
            play(video);
          }
        }, { once: true });
      }
    });
  }, { rootMargin: "300px 0px" });
  videos.forEach(function (video) {
    watcher.observe(video);
  });
})();
