(function () {
	'use strict';

	/*----------------------------------------
		Detect Mobile
	----------------------------------------*/
	var isMobile = {
		any: function () {
			return /Android|BlackBerry|iPhone|iPad|iPod|Opera Mini|IEMobile/i.test(navigator.userAgent);
		}
	};

	/*----------------------------------------
		Slider
	----------------------------------------*/
	var flexSlider = function () {
		jQuery('.flexslider').flexslider({
			animation: 'fade',
			prevText: '',
			nextText: '',
			slideshow: true
		});
	};

	/*----------------------------------------
		Animate on scroll
	----------------------------------------*/
	var contentWayPoint = function () {
		jQuery('.probootstrap-animate').waypoint(function (direction) {
			if (direction !== 'down' || jQuery(this.element).hasClass('probootstrap-animated')) {
				return;
			}
			jQuery(this.element).addClass('item-animate');
			setTimeout(function () {
				jQuery('body .probootstrap-animate.item-animate').each(function (k) {
					var el = jQuery(this);
					setTimeout(function () {
						var effect = el.data('animate-effect');
						if (effect === 'fadeIn') {
							el.addClass('fadeIn probootstrap-animated');
						} else if (effect === 'fadeInLeft') {
							el.addClass('fadeInLeft probootstrap-animated');
						} else if (effect === 'fadeInRight') {
							el.addClass('fadeInRight probootstrap-animated');
						} else {
							el.addClass('fadeInUp probootstrap-animated');
						}
						el.removeClass('item-animate');
					}, k * 30);
				});
			}, 100);
		}, { offset: '95%' });
	};

	/*----------------------------------------
		Navbar background after scroll
	----------------------------------------*/
	var navbarState = function () {
		var navbar = jQuery('.probootstrap-navbar');
		var ticking = false;
		var update = function () {
			navbar.toggleClass('scrolled', jQuery(window).scrollTop() > 5);
			ticking = false;
		};
		jQuery(window).on('scroll', function () {
			if (!ticking) {
				ticking = true;
				window.requestAnimationFrame(update);
			}
		});
		update();
	};

	/*----------------------------------------
		Parallax (desktop only)
	----------------------------------------*/
	var stellarInit = function () {
		if (!isMobile.any()) {
			jQuery(window).stellar();
		}
	};

	/*----------------------------------------
		Page navigation
	----------------------------------------*/
	var navActive = function (section) {
		var $el = jQuery('.navbar-nav');
		$el.find('li').removeClass('active');
		$el.find('a[data-nav-section="' + section + '"]').closest('li').addClass('active');
	};

	var clickMenu = function () {
		jQuery('.navbar-nav a:not([class="external"])').on('click', function (event) {
			var section = jQuery(this).data('nav-section');
			var target = jQuery('[data-section="' + section + '"]');
			if (jQuery('.navbar-toggle').is(':visible')) {
				jQuery('.navbar-toggle').click();
			}
			navActive(section);
			if (target.length) {
				jQuery('html, body').animate({ scrollTop: target.offset().top - 55 }, 500, 'easeInOutExpo');
			}
			event.preventDefault();
		});
	};

	var navigationSection = function () {
		var $section = jQuery('section[data-section]');
		$section.waypoint(function (direction) {
			if (direction === 'down') {
				navActive(jQuery(this.element).data('section'));
			}
		}, { offset: '150px' });
		$section.waypoint(function (direction) {
			if (direction === 'up') {
				navActive(jQuery(this.element).data('section'));
			}
		}, { offset: function () { return -jQuery(this.element).height() - 155; } });
	};

	/*----------------------------------------
		Schedule: highlight today (cards carry data-date="YYYY-MM-DD")
	----------------------------------------*/
	var scheduleToday = function () {
		var now = new Date();
		var pad = function (n) { return (n < 10 ? '0' : '') + n; };
		var iso = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
		jQuery('.schedule-day[data-date="' + iso + '"]').addClass('is-today');
	};

	jQuery(function () {
		scheduleToday();
		contentWayPoint();
		navbarState();
		stellarInit();
		clickMenu();
		navigationSection();
	});

	jQuery(window).on('load', function () {
		flexSlider();
	});
})();
