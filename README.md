# Cachelab

This is a small web application for asking some CPU cache related questions.

Two sets of questions are asked:

1.  given some parameters of a memory cache, filling in the other parameters
2.  given some parameters of a memory cache and a series of accesses, identify which are hits and misses, and for the misses, identify what is evicted in order to bring in the new item

The tool requires three sets of questions to be answered of the first type and one of the second type. Students can keep trying new questions until they get all questions correct.

# Setup

This program is a Django web application. To use it, first:

*  Figure out how you're handling authentication, see [the Authentication section below](#Authentication)
*  Edit `cachelabweb/settings.py` to change `ALLOWED_HOSTS`, `LOGIN_URL`, and `COURSE_WEBSITE`.
*  Do any customization of the questions you desire.

Then,you can run it as a standalone web application using `python manage.py 127.0.0.1:8888` (to bind to port 8888 on localhost). When not testing, I ran it using Nginx to act as an HTTPS server which acted as a reverse proxy to a uwsgi server as the backend. Configuration files used are in `config-templates`.

# Authentication

As this was used at the University of Virginia, this web application relies on logins being forwarded from another website for authentication (rather
than tying directly with a single-sign on system). The scripts used in Spring 2018 at the University of Virginia are in the `config-templates` directory:

To make this work, create a `cachelab/secret_settings.py` which contains code like

    SECRET_KEY = '...'

. Then, you could use the PHP script `config-templates/cachelab.php` (or the `-prompt` version is used) by modifying:

*  the URL in the `<form>` tag to point to the ocation running the web application
*  the `$key` variable to have the same value as the secret key in `SECRET_KEY` in `secret_settings.py`

along with a `staff.php` script that sets:

*  `$user` to the user ID of the user. This is the ID that will be used when extracting grading information from the web application. At the UVa, the PHP script ran an Apache webserver using the Shibboleth single-sign on authentication module, so `$user` could be set `$PHP_AUTH_USER`.
*  `$isstaff` set to true if the user is course staff, false otherwise. Setting this flag on login enables debugging information and access to grades.

## Alternate approaches

The web application uses built-in Django account support, so it should be fairly simple to use the built-in Django login support. You would
need to add:

*  identifying logged in users as staff based on their account instead of based on extra data passed on login and stored in the session.
*  removal of the forwarded login support from `cachelabweb/urls.py`

# Modifying the questions

Most of the code that generates the questions is in `quiz/models.py` (with the corresponding HTML generation and form processing code in
`quiz/views.py`). To change how random access patterns are generated edit the default parameters of the `random` method of `CachePattern`,
and the `random_parameters_for_pattern` function. To change how random cache parameters are selected for parameter
fill-in-the-blank questions, change the default parameters of the `random` method of `CacheParameters`.

To change the number of cache parametetr questions required before the tool indicates the user is done, change `NEEDED_PARAMETER_PERFECT` in
`quiz/views.py`.

# Retrieving grades

If you login as staff, there is an option to retrieve grades as a CSV file. The grade formula is hard-coded in `get_scores_csv`, and
gives 5 points for the parameter questions and 5 points for the pattern questions, with a minimum score of 5 for students who get
at least 2 points on their best 3 parameter questions (counting each question as 1 point). When retrieving the CSV file, you are required
to entire a due time, the CSV file retrieved will ignore all work done after that due time.

# Missing features / regrets

*  Students often get confused between a cache miss causing something to be evicted and that miss being a conflict miss. To help with this, it might be a good idea to ask whether each cache miss is a compulsory miss or not.

*  I didn't take advantage of Django's form generation support, which probably cost me a lot of time and elegance.
