from flask import Flask, redirect, url_for, session, request, jsonify, render_template, flash
from markupsafe import Markup
from flask_oauthlib.client import OAuth
from bson.objectid import ObjectId

import pprint
import os
import random
import pymongo
import sys
import datetime
 
app = Flask(__name__)

app.debug = False #Change this to False for production
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
    
@app.route('/page1', methods=['GET', 'POST'])
def renderPage1():
	if 'secret_number' not in session:
		session['secret_number'] = random.randint(0, 99)
		session['guess_made'] = 0
		session['guess_history'] = []
		session['game_message'] = 'pick a random integer from 0 to 00, you have 6 guesses.'
		
		if request.method == 'POST':
		    try:
			    user_guess = int(request.form.get('user_input'))
		    except ValueError:
			    session['game_message'] = 'Invalid input. Try again'
			    return render_template('game.html', message=session['game_message'], history=session['guess_history'], guesses_left=6 - session['guesses_made'])

		session['guesses_made'] +=1
		guesses_left = 6 - session['guesses_made']
		
		if user_guess == session['secret_number']:
			session['game_message'] = f"CORRECT The number was {session["secret_number"]}. Game over"

		elif session['guesses_made'] >= 6:
			session['game_message'] = f"GAME OVER The number was {session["secret_number"]}. Game over"
			
#def get_minute_specific_number(lower_bound, upper_bound):
    #"""
    #Generates a consistent number for the current minute using the minute 
    #of the hour as the random seed.
    #"""
    # 1. Get the current time.
    #now = datetime.datetime.now()
    
    # 2. Extract the current minute (an integer between 0 and 59).
    #current_minute = now.minute
    
    # 3. Use the minute as the seed for the random number generator.
    # Seeding ensures the number generated is the same for the entire minute.
    #random.seed(current_minute)
    
    # 4. Generate the "random" number within the specified range.
    # Use randint for inclusive range.
    #result = random.randint(lower_bound, upper_bound)
    
    #return result

## Generate a number between 1 and 100 that is the same for the current minute.
#number = get_minute_specific_number(1, 100)
#print(f"The consistent number for this minute is: {number}")


#context processors run before templates are rendered and add variable(s) to the template's context
#context processors must return a dictionary 
#this context processor adds the variable logged_in to the conext for all templates
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
        now = datetime.datetime.now(datetime.UTC)

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
    return render_template('message.html', message=message)

# @app.route('/page1')
# def renderPage1():
#     return render_template('page1.html')

@app.route('/page2')
def renderPage2():
    if 'user_data' not in session:
        return redirect(url_for('home'))
    
    github_id = session['user_data']['id']
    user = collection.find_one({"github_id": github_id})
    
    if not user:
        flash("No user record found.")
        return redirect(url_for('home'))
    
    return render_template('page2.html', user=user)
    return render_template('page2.html')
 
@app.route('/update_p')
def update():
    return Markup("<p>This text came from the server.</p>")
    
    
    
#the tokengetter is automatically called to check who is logged in.
@github.tokengetter
def get_github_oauth_token():
    return session['github_token']


if __name__ == '__main__':
    app.run()
