from flask import Flask, redirect, url_for, session, request, jsonify, render_template, flash
from markupsafe import Markup
from flask_oauthlib.client import OAuth
from bson.objectid import ObjectId
import datetime
from datetime import timedelta

import pprint
import os
import random
import pymongo
import sys
import datetime
import pytz
 
app = Flask(__name__)

app.debug = True #Change this to False for production
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' #Remove once done debugging

app.secret_key = os.environ['SECRET_KEY'] #used to sign session cookies
oauth = OAuth(app)
oauth.init_app(app) #initialize the app to be able to make requests for user information

#Set up GitHub as OAuth provider
github = oauth.remote_app(
    'github',
    consumer_key=os.environ['GITHUB_CLIENT_ID'], #your web app's "username" for github's OAuth
    consumer_secret=os.environ['GITHUB_CLIENT_SECRET'],#your web app's "password" for github's OAuth
    request_token_params={'scope': 'user:email'}, #request read-only access to the user's email.  For a list of possible scopes, see developer.github.com/apps/building-oauth-apps/scopes-for-oauth-apps
    base_url='https://api.github.com/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://github.com/login/oauth/access_token',  
    authorize_url='https://github.com/login/oauth/authorize' #URL for github's OAuth login
)

#Connect to database
url = os.environ["MONGO_CONNECTION_STRING"]
client = pymongo.MongoClient(url)
db = client[os.environ["MONGO_DBNAME"]]
collection = db['userinfo'] #TODO: put the name of the collection here

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
    
@app.route('/api/can_play')
def can_play():
    if not ('github_token' in session):
        return jsonify({'can_play': False, 'reason': 'not_logged_in'})
    user_id = session['user_data']['id']
    user_doc = collection.find_one({'github_id': user_id})
    now = datetime.datetime.now(pytz.UTC).date()
    if user_doc and 'last_play_date' in user_doc:
        last_play_date = datetime.datetime.fromisoformat(user_doc['last_play_date']).date()
        if now == last_play_date:
            return jsonify({'can_play': False, 'reason': 'already_played_today'})
    return jsonify({'can_play': True})

@app.route('/playhere', methods=['GET', 'POST'])
def renderPlayhere():
    if ('github_token' not in session):
        return redirect(url_for('login'))
        
    user_id = session['user_data']['id']
    username = session['user_data']['login']
    
    user_guess = None
    secret_number = None
    won = False
    message = 'Guess the number from 0 to 99! You have 6 attempts'
    guesses_made = 0
    history = []
    guesses_left = 6
    
#     session.pop('secret_number', None)
#     session.pop('guesses_made', None)
#     session.pop('guess_history', None)
#     session.pop('game_message', None)
    
    now = datetime.datetime.now(pytz.UTC).date()
    
    #if already played today
    user_doc = collection.find_one({'github_id': user_id})
    finished_today = False
    
    #print(request.form.get('user_input'))
    #user_guess = int(request.form.get('user_input'))
    #print(secret_number)
    #print(user_guess)
    
    if user_doc and 'last_play_date' in user_doc:
    	last_play_date = datetime.datetime.fromisoformat(user_doc['last_play_date']).date()
    	if now == last_play_date:
    	    finished_today = True
    	    
    today_game = collection.find_one({'github_id': user_id, 'game_date': now.isoformat()})
    
    if finished_today:
        today_game = collection.find_one({'github_id': user_id, 'game_date': now.isoformat()})
        score_doc = db['daily_scores'].find_one({'github_id': user_id, 'date': now.isoformat()})
        
        if score_doc:
            tries = score_doc.get('guesses', 0)
            won_flag = score_doc.get('won', False)
            secret_number = today_game.get('secret_number', 'unknown')
            message = f"You've already played today. You {'won' if won_flag else 'lost'}! The number was {secret_number}. You took {tries} {'try' if tries == 1 else 'tries'}."
        else:
            message = f"You've already played today. Check back tomorrow."
        
        history = today_game.get('guess_history', []) if today_game else []

        return render_template('playhere.html', message=message, history=[], guesses_left=0)

     
    #elif user_guess == secret_number:
        #game_message = f'CORRECT! the number was {secret_number}.Game over'
        #won = True  
     
    if not today_game:
        secret_number = random.randint(0, 99)
        guesses_made = 0
        history = []
        message = 'Guess the number from 0 to 99! you have 6 attempts' 
        collection.update_one(
            {'github_id': user_id},
            {'$set': {
                'game_date': now.isoformat(),
                'secret_number': secret_number,
                'guesses_made': 0,
                'guess_history': [],
                'game_message': message,
                'game_active': True,
                'won': False
            }},
            upsert=True
        )
    else:
        secret_number = today_game['secret_number']
        guesses_made = today_game['guesses_made']
        history = today_game['guess_history']
        message = today_game.get('game_message', 'Guess the number from 0 to 99!')
    
    guesses_left = 6 - guesses_made
    
    #user_guess = int(request.form.get('user_input'))
    #print(secret_number)
    #print(user_guess)
    
    if request.method == 'POST' and guesses_left > 0:
        try:
            user_guess = int(request.form.get('user_input'))
        except (TypeError, ValueError):
            message = 'Invalid input. Try again'
            #collection.update_one(
                #{'github_id': user_id, 'game_date': now.isoformat()},
                #{'$set': {'game_message': game_message}}
            #)
        else:
            guesses_made += 1
            guesses_left = 6 - guesses_made
            won = False
        
            if user_guess == secret_number:
                message = f'CORRECT The number was {secret_number}. Game over'
                won = True

                guesses_left = 0

                collection.update_one(
                    {'github_id': user_id},
                    {'$set': {'last_play_date': now.isoformat(), 'last_score': guesses_made, 'game_active': False, 'won': True}},
                    upsert=True
                )
            
                db['daily_scores'].insert_one({
                    'github_id': user_id,
                    'username': username,
                    'date': now.isoformat(),
                    'guesses': guesses_made,
                    'won': True
                })
            
            elif guesses_made >= 6:
                message = f'GAME OVER! The number was {secret_number}'
                history.append(f'You guessed {user_guess}: Game Over')
                collection.update_one(
                    {'github_id': user_id},
                    {'$set': {'last_play_date': now.isoformat()}},
                    upsert=True
                )
                db['daily_scores'].insert_one({
                    'github_id': user_id,
                    'username': username,
                    'date': now.isoformat(),
                    'guesses': guesses_made,
                    'won': False
                })
            
            elif user_guess < secret_number:
                message = 'Too low'
                history.append(f'You guessed {user_guess}: Too low')
            else:
                message = 'Too high'
                history.append(f'You guessed {user_guess}: Too high')
             
            collection.update_one(

                {'github_id': user_id, 'game_date': now.isoformat()},
                {'$set': {'guesses_made': guesses_made, 'guess_history': history, 'game_message': message, 'won': won }}

            )
        
            today_game = collection.find_one({'github_id': user_id, 'game_date': now.isoformat()})
            if today_game:
                history = today_game['guess_history']
                message = today_game.get('game_message', message)
                guesses_left = 6 - today_game['guesses_made']
                won = today_game.get('won', won)
            
    return render_template('playhere.html', message=message, history=history, guesses_left=guesses_left, won=won)

@app.context_processor
def inject_logged_in():
    return {"logged_in":('github_token' in session)}

@app.route('/')
def home():
    return render_template('home.html')

#redirect to GitHub's OAuth page and confirm callback URL
@app.route('/login')
def login():   
    return github.authorize(callback=url_for('authorized', _external=True, _scheme='http')) #callback URL must match the pre-configured callback URL

@app.route('/logout')
def logout():
    session.clear()
    flash('You were logged out.')
    return redirect('/')

@app.route('/login/authorized')
def authorized():
    resp = github.authorized_response()
    if resp is None:
        session.clear()
        flash(
            'Access denied: reason=' + request.args['error'] +
            ' error=' + request.args['error_description'] +
            ' full=' + pprint.pformat(request.args),
            'error'
        )
        return redirect(url_for('home'))
    try:
        session['github_token'] = (resp['access_token'], '')
        session['user_data'] = github.get('user').data
        user = session['user_data']

        github_id = user['id']
        username = user['login']
        avatar_url = user.get('avatar_url')
        html_url = user.get('html_url')
        email = user.get('email')
        now = datetime.datetime.now(pytz.UTC)

        existing = collection.find_one({"github_id": github_id})

        if existing:
            last_login = existing.get("last_login")
            current_streak = existing.get("current_streak", 0)
            longest_streak = existing.get("longest_streak", 0)

            if last_login is not None:
                delta_days = (now.date() - last_login.date()).days
                if delta_days == 1:
                    current_streak += 1
                elif delta_days == 0:
                    pass
                else:
                    current_streak = 1
            else:
                current_streak = 1

            if current_streak > longest_streak:
                longest_streak = current_streak

            collection.update_one(
                {"github_id": github_id},
                {
                    "$set": {
                        "username": username,
                        "avatar_url": avatar_url,
                        "html_url": html_url,
                        "email": email,
                        "last_login": now,
                        "current_streak": current_streak,
                        "longest_streak": longest_streak,
                    }
                }
            )
        else:
            current_streak = 1
            longest_streak = 1
            collection.insert_one(
                {
                    "github_id": github_id,
                    "username": username,
                    "avatar_url": avatar_url,
                    "html_url": html_url,
                    "email": email,
                    "last_login": now,
                    "current_streak": current_streak,
                    "longest_streak": longest_streak,
                }
            )
        message = 'You were successfully logged in as ' + username + '.'
    except Exception as inst:
        session.clear()
        print(inst)
        message = 'Unable to login, please try again.'
        
      
    if 'github_token' not in session:
        return redirect(url_for('home'))
    username = session['user_data']['login']
    user_posts = list(collection.find({"username": username}))
    
    userstuff = list(collection.find().sort("_id", -1))
    for userinfo in userstuff:
        userinfo['_id'] = str(userinfo['_id'])
    
    return render_template('message.html', message=message, userstuff=userstuff, username=username)

# @app.route('/page1')
# def renderPage1():
#     return render_template('page1.html')

@app.route('/scoreboard')
def renderScoreboard():
    if 'user_data' not in session:
        return redirect(url_for('home'))
    
    github_id = session['user_data']['id']
    user = collection.find_one({"github_id": github_id})
    
    if not user:
        flash("No user record found.")
        return redirect(url_for('home'))
    

    return render_template('scoreboard.html', user=user)

    if user :
        user['_id'] = str(user['_id'])
    return render_template('page2.html', user=user)

    #return render_template('page2.html')
 
@app.route('/update_p')
def update():
    return Markup("<p>This text came from the server.</p>")
    
    
    
#the tokengetter is automatically called to check who is logged in.
@github.tokengetter
def get_github_oauth_token():
    return session['github_token']


if __name__ == '__main__':
    app.run()
