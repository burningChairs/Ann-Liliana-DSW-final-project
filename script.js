$(document).ready(function(){
    checkCanPlay();
    
    $('form').submit(function(e) {
        if (!checkCanPlaySync()) {
            e.preventDefault();
            return false;
        }
    });
});

function checkCanPlay() {
    $.getJSON('/api/can_play', function (data) {
        if (!data.can_play) {
            if (data.reason === 'not_logged_in'){
                window.location.href = '/login';
            } else {
                showCooldown(data.sounds_left);
            }
        }
    });
}

function checkCanPlaySync() {
    var canPlay = true;
    $.ajax({
        url: '/api/can_play',
        async: false,
        success: function(data) {
            canPlay = data.can_play;
        }
    });
    return canPlay;
}

function showCooldown(seconds) {
    var minutes = Math.floor(seconds / 60);
    var secs = seconds % 60;
    $('#game_message').text('Cooldown active: ${minutes}m ${secs}s remaining');
    $('#user_input, button[type="submit"]').prop('disabled', true);
    
    var timer = setInterval(function() {
        seconds--;
        if (seconds <= 0) {
            clearInterval(timer);
            location.reload();
        } else {
            var m = Math.floor(seconds / 60);
            var s = seconds % 60;
            $('#game_message').text('Cooldown: ${m}m ${s}s');
        }
    }, 1000);
}