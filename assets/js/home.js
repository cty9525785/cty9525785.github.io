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
  // On a phone the slides lie side by side in a strip that moves under the finger (home.css; Tianyu: "Can we make
  // this slidable on phone view"): the roll, the tabs and the arrows over the clip scroll it to their slide, a swipe
  // shows the slide it stops on, and the roll waits while a finger is down.
  var DWELL = 9000;  // ms a slide shows, at least
  var ARROWS = 3000;  // ms a phone's arrows stay after they show or a finger leaves the slides
  var box = document.querySelector(".highlights");
  if (box) {
    var slides = Array.prototype.slice.call(box.querySelectorAll(".slide"));
    var tabs = Array.prototype.slice.call(box.querySelectorAll(".hl-tab"));
    var pause = box.querySelector(".hl-pause");
    var strip = box.querySelector(".hl-slides");
    var phone = window.matchMedia("(max-width: 860px)");  // home.css's phone layout
    var at = 0;
    var paused = false;
    var onScreen = true;
    var timer = null;
    var timed = false;  // the shown slide's clip has set the roll's time
    var touching = false;
    var target = -1;  // the slide the script is scrolling the strip to, until it gets there
    var settling = null;

    var offset = function (i) {
      return slides[i].offsetLeft - slides[0].offsetLeft;
    };

    var clip = function (i) {
      return slides[i].querySelector("video");
    };
    var visible = function () {
      return onScreen && !document.hidden;
    };

    // A clip plays as soon as its slide shows: a phone loads a clip only when asked to play it (an iPhone never
    // preloads one). Its poster lies over it until it plays (home.css), so a clip still loading, or one a phone will
    // not play, shows a still rather than a black frame.
    var start = function (video) {
      play(video);
    };
    slides.forEach(function (slide, i) {
      var video = slide.querySelector("video");
      if (video) {
        video.addEventListener("playing", function () {
          video.parentNode.classList.add("playing");
          // Now its length is known and it has begun, however late: the roll waits for all of it. Once per showing,
          // since a looping clip may report playing again.
          if (i === at && !timed) {
            timed = true;
            schedule();
          }
        });
      }
    });

    var schedule = function () {
      window.clearTimeout(timer);
      if (paused || touching || !visible()) {
        return;
      }
      var video = clip(at);
      var length = video && isFinite(video.duration) ? (video.duration - video.currentTime) * 1000 : 0;
      timer = window.setTimeout(function () {
        show((at + 1) % slides.length);
      }, Math.max(DWELL, length));
    };

    var begin = function (i) {
      var video = clip(i);
      if (video && !paused && visible()) {
        if (video.readyState >= 2) {  // only a clip with frames rewinds: rewinding one without hides Safari's poster
          video.currentTime = 0;
        }
        start(video);
      }
    };

    var show = function (i, swiped) {
      timed = false;
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
      // When the strip moves to a slide, its clip starts once the slide is in view (settle, below), never while it is
      // still off screen: Safari pauses muted autoplaying video it cannot see.
      if (phone.matches && !swiped && Math.abs(strip.scrollLeft - offset(i)) >= 1) {
        target = i;
        strip.scrollTo({ left: offset(i), behavior: "smooth" });
      } else {
        begin(i);
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
    // The arrows over a phone's clip (Tianyu: "Yes add the buttons") step like the tabs, and the roll goes on.
    var prevArrow = box.querySelector(".hl-prev");
    var nextArrow = box.querySelector(".hl-next");
    prevArrow.addEventListener("click", function () {
      show((at + slides.length - 1) % slides.length);
    });
    nextArrow.addEventListener("click", function () {
      show((at + 1) % slides.length);
    });
    // They fade so they don't cover the clip (Tianyu: "make the arrows disappear aftera while"), showing again when they
    // come into view, for a pointer or the keyboard, and when a finger lifts from the slides without having scrolled the
    // page. Only on the lift: shown under a finger that just landed, an arrow would stop a swipe that starts there from
    // moving the strip. The roll moving on does not bring them back.
    var arrows = box.querySelector(".hl-arrows");
    var stage = box.querySelector(".hl-stage");
    var fading = null;
    var pageAt = 0;
    var showArrows = function () {
      arrows.classList.remove("faded");
      window.clearTimeout(fading);
      fading = window.setTimeout(function () {
        arrows.classList.add("faded");
      }, ARROWS);
    };
    stage.addEventListener("touchstart", function () {
      pageAt = window.scrollY;
    }, { passive: true });
    stage.addEventListener("touchend", function () {
      if (window.scrollY === pageAt) {
        showArrows();
      }
    });
    stage.addEventListener("mousemove", showArrows);
    stage.addEventListener("focusin", showArrows);

    // Once the strip stops, the slide it stopped on shows: one the script scrolled to is already showing and its clip
    // starts now, and the slides it passes on the way (back from the last to the first) are not shown.
    var settle = function () {
      if (!phone.matches || touching) {
        return;
      }
      var i = Math.round(strip.scrollLeft / (slides.length > 1 ? offset(1) : 1));
      i = Math.max(0, Math.min(slides.length - 1, i));
      if (target >= 0 && i !== target) {
        return;
      }
      var arrived = target === i;
      target = -1;
      if (i !== at) {
        show(i, true);
      } else {
        if (arrived) {
          begin(i);
        }
        schedule();
      }
    };
    var later = function () {
      window.clearTimeout(settling);
      settling = window.setTimeout(settle, 150);
    };

    // The current number's dark chip moves along the row with the strip (home.css; Tianyu: "make it moving along with
    // the sliding card"): a dark pill over the numbers, holding them again in white, follows the strip's place each
    // frame, its white numbers shifted back so each stays on its chip. It only shows where the strip is; the slide
    // that shows, and its clip, still change once the strip stops.
    var nav = box.querySelector(".hl-tabs");
    var pill = document.createElement("span");
    var copy = document.createElement("span");
    pill.className = "hl-pill";
    copy.className = "hl-pill-numbers";
    pill.setAttribute("aria-hidden", "true");
    tabs.forEach(function (tab) {
      var number = document.createElement("span");
      number.textContent = tab.textContent;
      copy.appendChild(number);
    });
    pill.appendChild(copy);
    nav.appendChild(pill);
    var frame = null;
    var glide = function () {
      frame = null;
      if (!phone.matches) {
        return;
      }
      var row = nav.getBoundingClientRect();
      var lefts = tabs.map(function (tab) {
        return tab.getBoundingClientRect().left - row.left;
      });
      var place = Math.max(0, Math.min(tabs.length - 1, strip.scrollLeft / (slides.length > 1 ? offset(1) : 1)));
      var i = Math.max(0, Math.min(Math.floor(place), tabs.length - 2));
      var x = tabs.length > 1 ? lefts[i] + (lefts[i + 1] - lefts[i]) * (place - i) : lefts[0];
      pill.style.width = tabs[0].getBoundingClientRect().width + "px";
      copy.style.width = row.width + "px";
      pill.style.transform = "translateX(" + x + "px)";
      copy.style.transform = "translateX(" + -x + "px)";
    };
    var follow = function () {
      if (frame === null) {
        frame = window.requestAnimationFrame(glide);
      }
    };
    strip.addEventListener("scroll", follow, { passive: true });
    window.addEventListener("resize", follow);
    strip.addEventListener("scroll", later);
    strip.addEventListener("touchstart", function () {
      touching = true;
      target = -1;
      window.clearTimeout(timer);
    }, { passive: true });
    ["touchend", "touchcancel"].forEach(function (name) {
      strip.addEventListener(name, function () {
        touching = false;
        later();
      });
    });
    strip.addEventListener("wheel", function () {
      target = -1;
    }, { passive: true });
    if (phone.addEventListener) {
      phone.addEventListener("change", function () {
        if (phone.matches) {
          strip.scrollLeft = offset(at);
          follow();
        }
      });
    }
    document.addEventListener("visibilitychange", resume);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (items) {
        onScreen = items[items.length - 1].isIntersecting;
        resume();
      }).observe(box);
      new IntersectionObserver(function (items) {
        if (items[items.length - 1].isIntersecting) {
          showArrows();
        }
      }, { threshold: 0.9 }).observe(nextArrow);
    }
    show(0);
    follow();
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
