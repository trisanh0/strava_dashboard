/**
 * Main.gs
 * Core logic for fetching activities and sending notifications.
 */

/**
 * Main routine: Fetches, filters, and logs new activities for all authorized athletes.
 */
function fetchClubActivities() {
    const athletes = getStoredAthletes();
    if (athletes.length === 0) {
        Logger.log('No authorized athletes found. Run logAuthUrl() to get the onboarding Web App link.');
        return;
    }

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Data');
    const lastRow = sheet.getLastRow();
    const existingIds = lastRow > 1
        ? sheet.getRange(2, 1, lastRow - 1, 1).getValues().flat().map(String)
        : [];

    const newRows = [];

    // Calculate timestamp for 7 days ago to avoid fetching ancient history
    const sevenDaysAgoSeconds = Math.floor((Date.now() - (7 * 24 * 60 * 60 * 1000)) / 1000);

    athletes.forEach(athlete => {
        const accessToken = refreshAccessToken(athlete.refreshToken, athlete.appId || '1');
        if (!accessToken) {
            Logger.log(`Skipping athlete ${athlete.firstName} (${athlete.athleteId}): Token refresh failed.`);
            return;
        }

        const url = `https://www.strava.com/api/v3/athlete/activities?after=${sevenDaysAgoSeconds}&per_page=50`;
        let userActivities = [];

        try {
            const response = UrlFetchApp.fetch(url, {
                headers: { Authorization: `Bearer ${accessToken}` },
                muteHttpExceptions: true
            });
            if (response.getResponseCode() === 200) {
                userActivities = JSON.parse(response.getContentText());
            } else {
                Logger.log(`Error fetching activities for ${athlete.firstName}: ${response.getResponseCode()} - ${response.getContentText()}`);
            }
        } catch (e) {
            Logger.log(`Fetch error for ${athlete.firstName}: ${e.message}`);
        }

        userActivities.forEach(act => {
            const firstName = toTitleCase(athlete.firstName || (act.athlete ? act.athlete.firstname : 'Athlete'));
            const lastName = (athlete.lastName || (act.athlete ? act.athlete.lastname : '')).replace(/\s+/g, '_');
            const athleteKey = `${firstName}_${lastName}`;
            const uniqueId = `${athleteKey}_${act.distance}_${act.moving_time}_${act.name}`.replace(/\s+/g, '_');

            if (existingIds.includes(uniqueId)) return;
            if (newRows.some(row => row[0] === uniqueId)) return;

            const dateStr = act.start_date_local || act.start_date;
            const date = dateStr ? new Date(dateStr) : new Date();
            const distKm = (act.distance || 0) / 1000;
            const durationMin = (act.moving_time || 0) / 60;
            const paceDecimal = distKm > 0 ? Number((durationMin / distKm).toFixed(2)) : 0;
            const team = getTeam(firstName);
            const effectiveDistKm = getEffectiveDistance(distKm, act.type, firstName, paceDecimal);

            newRows.push([
                uniqueId, firstName, team, date,
                Number(distKm.toFixed(2)), effectiveDistKm,
                Number(durationMin.toFixed(2)), paceDecimal,
                act.total_elevation_gain || 0, act.type
            ]);
        });
    });

    if (newRows.length > 0) {
        sheet.getRange(lastRow + 1, 1, newRows.length, newRows[0].length).setValues(newRows);
        Logger.log(`Added ${newRows.length} items from ${athletes.length} athletes.`);
        sendDiscordNotification(newRows);
    } else {
        Logger.log(`No new activities found across ${athletes.length} athletes.`);
    }
}

/**
 * Sends a formatted notification to Discord for new activities.
 */
function sendDiscordNotification(newActivities) {
    if (!DISCORD_WEBHOOK_URL) {
        Logger.log('DISCORD_WEBHOOK_URL not set. Skipping notification.');
        return;
    }

    const filteredActivities = newActivities.filter(act => {
        const dist = act[4];
        const type = act[9];
        return type !== 'Walk' || dist > 1.0;
    });

    if (filteredActivities.length === 0) {
        Logger.log('No qualifying activities for Discord notification.');
        return;
    }

    const embeds = filteredActivities.map(act => {
        const [id, name, team, date, dist, effDist, duration, pace, elevation, type] = act;
        const multiplier = getMultiplier(type, name, pace);

        return {
            color: DISCORD_COLOR,
            fields: [
                { name: 'Distance', value: `${dist.toFixed(2)} km`, inline: true },
                { name: 'Multiplier', value: `${multiplier.toFixed(2)}x`, inline: true },
                { name: 'Effort', value: `${effDist.toFixed(2)}`, inline: true },
                { name: 'Duration', value: `${duration.toFixed(2)} min`, inline: true },
                { name: 'Pace', value: `${formatDuration(pace)}/km`, inline: true },
                { name: 'Elevation', value: `${elevation} m`, inline: true },
                { name: 'Team', value: team, inline: true },
            ],
            timestamp: new Date(date).toISOString()
        };
    });

    for (let i = 0; i < filteredActivities.length; i++) {
        // Pre-request delay: 2s between messages to stay within 5 req/2s bucket
        if (i > 0) {
            Utilities.sleep(2000);
        }

        const act = filteredActivities[i];
        const name = act[1];
        const type = act[9];
        
        const discordId = DISCORD_IDS[name];
        const mention = (discordId && discordId !== '') ? `<@${discordId}>` : name;

        const randomMessage = DISCORD_PHRASES[Math.floor(Math.random() * DISCORD_PHRASES.length)]
            .replace('{name}', mention)
            .replace('{type}', type);

        const payload = {
            content: randomMessage,
            embeds: [embeds[i]]
        };

        const options = {
            method: 'post',
            contentType: 'application/json',
            payload: JSON.stringify(payload),
            muteHttpExceptions: true
        };

        let success = false;
        let retries = 0;
        const maxRetries = 3;

        while (!success && retries <= maxRetries) {
            try {
                const response = UrlFetchApp.fetch(DISCORD_WEBHOOK_URL, options);
                const responseCode = response.getResponseCode();
                const headers = response.getHeaders();

                if (responseCode >= 200 && responseCode < 300) {
                    success = true;

                    // Proactive throttle: if the bucket is nearly exhausted, wait for it to reset
                    const remaining = headers['X-RateLimit-Remaining'] || headers['x-ratelimit-remaining'];
                    const resetAfter = headers['X-RateLimit-Reset-After'] || headers['x-ratelimit-reset-after'];
                    if (remaining !== undefined && parseInt(remaining, 10) <= 1 && resetAfter) {
                        const resetMs = Math.round(parseFloat(resetAfter) * 1000) + 500;
                        Logger.log(`Bucket nearly empty (${remaining} remaining). Waiting ${resetMs}ms for reset.`);
                        Utilities.sleep(resetMs);
                    }
                } else if (responseCode === 429) {
                    // retry_after is always a float in seconds (per Discord docs)
                    let waitMs = 2000; // Default fallback

                    try {
                        const body = JSON.parse(response.getContentText());
                        if (body.retry_after) {
                            waitMs = Math.round(body.retry_after * 1000);
                        }
                    } catch (e) {
                        // Fallback to Retry-After header (also in seconds)
                        const retryAfterHeader = headers['Retry-After'] || headers['retry-after'];
                        if (retryAfterHeader) {
                            waitMs = Math.round(parseFloat(retryAfterHeader) * 1000);
                        }
                    }
                    
                    waitMs += 500; // Buffer to avoid edge-of-window retries
                    if (waitMs > 30000) waitMs = 30000; // Cap at 30s to stay within GAS limits
                    
                    Logger.log(`Rate limited (429). Waiting ${waitMs}ms before retry... (Attempt ${retries + 1}/${maxRetries + 1})`);
                    Utilities.sleep(waitMs);
                    retries++;
                } else {
                    Logger.log(`Unexpected Discord error: ${responseCode} - ${response.getContentText()}`);
                    break;
                }
            } catch (e) {
                Logger.log(`Fetch error during Discord notification: ${e.message}`);
                Utilities.sleep(2000 * (retries + 1));
                retries++;
            }
        }
        
        if (!success) {
            Logger.log(`Failed to send notification for ${name} after ${retries} attempts.`);
        }
    }
    Logger.log(`Finished processing Discord notifications.`);
}
