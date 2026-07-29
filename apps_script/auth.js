/**
 * Auth.gs
 * Strava OAuth2 per-user authentication, Web App callbacks, and token refreshes.
 */

/**
 * Web App entry point for user authorization and OAuth redirect callbacks.
 */
function doGet(e) {
  const params = e ? e.parameter : {};
  const webAppUrl = ScriptApp.getService().getUrl();

  // Step 2: Handle OAuth Callback from Strava
  if (params.code) {
    return handleOAuthCallback(params, webAppUrl);
  }

  // Step 1: Handle User Connect Request or Landing Page
  const appId = params.app || '1';
  const state = params.state || appId;
  const creds = getApiCredentials(state);

  const authUrl = `https://www.strava.com/oauth/authorize?client_id=${creds.clientId}&response_type=code&redirect_uri=${encodeURIComponent(webAppUrl)}&approval_prompt=force&scope=read,activity:read_all&state=${state}`;

  if (params.connect === 'true') {
    return HtmlService.createHtmlOutput(`
      <html>
        <head><meta http-equiv="refresh" content="0; url=${authUrl}" /></head>
        <body><p>Redirecting to Strava authorization...</p></body>
      </html>
    `);
  }

  // General Onboarding Landing Page
  return HtmlService.createHtmlOutput(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>Sleep Comp - Connect Strava</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 40px 20px; background: #0e1117; color: #ffffff; }
          .card { background: #161b22; max-width: 480px; margin: 0 auto; padding: 30px; border-radius: 12px; border: 1px solid #30363d; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
          h1 { color: #fc5200; margin-bottom: 8px; }
          p { color: #8b949e; line-height: 1.5; font-size: 15px; }
          .btn { display: inline-block; margin: 10px; padding: 12px 24px; background: #fc5200; color: #fff; text-decoration: none; font-weight: bold; border-radius: 6px; }
          .btn:hover { background: #e04800; }
          .btn-sec { background: #21262d; border: 1px solid #30363d; }
          .btn-sec:hover { background: #30363d; }
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Sleep Comp Strava Sync</h1>
          <p>Connect your Strava account to automatically sync your activities to the Sleep Comp leaderboard.</p>
          <div style="margin-top: 24px;">
            <a href="${webAppUrl}?connect=true&app=1" class="btn">Connect (App Key 1 / Team Srikar)</a>
            <a href="${webAppUrl}?connect=true&app=2" class="btn btn-sec">Connect (App Key 2 / Team Ravi)</a>
          </div>
        </div>
      </body>
    </html>
  `);
}

/**
 * Handles OAuth callback when Strava redirects back with authorization code.
 */
function handleOAuthCallback(params, webAppUrl) {
  const code = params.code;
  const appId = params.state || '1';
  const creds = getApiCredentials(appId);

  const payload = {
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    code: code,
    grant_type: 'authorization_code'
  };

  try {
    const response = UrlFetchApp.fetch('https://www.strava.com/oauth/token', {
      method: 'post',
      payload: payload,
      muteHttpExceptions: true
    });

    const data = JSON.parse(response.getContentText());

    if (data.access_token && data.athlete) {
      const athlete = data.athlete;
      const athleteData = {
        athleteId: String(athlete.id),
        firstName: athlete.firstname || '',
        lastName: athlete.lastname || '',
        refreshToken: data.refresh_token,
        appId: appId,
        updatedAt: new Date().toISOString()
      };

      saveAthleteToken(athlete.id, athleteData);

      return HtmlService.createHtmlOutput(`
        <!DOCTYPE html>
        <html>
          <head>
            <title>Success!</title>
            <style>
              body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 50px 20px; background: #0e1117; color: #ffffff; }
              .card { background: #161b22; max-width: 440px; margin: 0 auto; padding: 32px; border-radius: 12px; border: 1px solid #238636; }
              h1 { color: #2ea043; }
              p { color: #c9d1d9; }
            </style>
          </head>
          <body>
            <div class="card">
              <h1>Connected Successfully!</h1>
              <p>Thanks, <strong>${athlete.firstname}</strong>! Your Strava account is now connected to Sleep Comp.</p>
              <p>You can close this browser tab.</p>
            </div>
          </body>
        </html>
      `);
    } else {
      return HtmlService.createHtmlOutput(`<h2>Authorization Failed</h2><p>${data.message || 'Unknown error'}</p>`);
    }
  } catch (e) {
    return HtmlService.createHtmlOutput(`<h2>Error</h2><p>${e.message}</p>`);
  }
}

/**
 * Refreshes short-lived access token using stored refresh token and Client ID/Secret.
 */
function refreshAccessToken(refreshToken, appId) {
  const creds = getApiCredentials(appId);
  const payload = {
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    refresh_token: refreshToken,
    grant_type: 'refresh_token'
  };

  const response = UrlFetchApp.fetch('https://www.strava.com/oauth/token', {
    method: 'post',
    payload: payload,
    muteHttpExceptions: true
  });

  const data = JSON.parse(response.getContentText());
  if (data.access_token) {
    return data.access_token;
  } else {
    Logger.log(`Failed to refresh token for app ${appId}: ${data.message || response.getContentText()}`);
    return null;
  }
}

/**
 * Log onboarding Web App URL to Apps Script console.
 */
function logAuthUrl() {
  const webAppUrl = ScriptApp.getService().getUrl();
  Logger.log('Share this Web App URL with your athletes: %s', webAppUrl);
}
