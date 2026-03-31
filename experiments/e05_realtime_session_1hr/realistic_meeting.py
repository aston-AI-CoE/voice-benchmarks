"""Realistic meeting transcript for session testing.

This is NOT a clean, structured script. It simulates how real meetings
actually sound:

- People interrupt each other
- Tangents and side conversations
- Implicit references ("that thing", "what he said")
- Numbers mentioned casually, not announced
- Decisions buried in discussion, not declared
- Filler ("um", "so yeah", "anyway")
- Topic jumping and circling back
- People disagreeing, changing their minds
- Small talk mixed with substance

The model is NOT told to "remember everything". It's just a meeting
assistant sitting in on the call.

Supports two modes:
1. Built-in realistic transcript (default)
2. External transcript file (from Whisper, Otter.ai, etc.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MeetingLine:
    """A single line of meeting dialogue."""
    speaker: str
    text: str
    minute: int  # approximate minute in the meeting
    delay_seconds: float = 0  # real-time delay before this line


@dataclass
class PostMeetingQuestion:
    """A question a real user would ask Otto after a meeting."""
    question_id: str
    question: str
    ground_truth: str  # what the correct answer should contain
    category: str  # "action_item", "decision", "detail", "inference", "ambiguous"
    difficulty: str  # "easy", "medium", "hard"
    source_minute: int  # roughly when the answer was discussed


@dataclass
class MidMeetingQuestion:
    """A casual mid-meeting question (like a real user would ask)."""
    trigger_after_minute: int
    question: str
    ground_truth: str


@dataclass
class HallucinationProbe:
    """Something that sounds like it could have been discussed but wasn't."""
    probe_id: str
    question: str


@dataclass
class RealisticMeeting:
    """Complete realistic meeting package."""
    title: str
    lines: list[MeetingLine]
    mid_meeting_questions: list[MidMeetingQuestion]
    post_meeting_questions: list[PostMeetingQuestion]
    hallucination_probes: list[HallucinationProbe]
    duration_minutes: int = 60


# ---------------------------------------------------------------------------
# The system prompt — NO priming, just "you're in a meeting"
# ---------------------------------------------------------------------------

REALISTIC_SYSTEM_PROMPT = """\
You are Otto, an AI assistant joining a team meeting. You're here to help \
if anyone asks you a question during the meeting, and to be available \
for follow-up questions after the meeting ends.

Just listen naturally. Don't take notes unless asked. Don't summarize \
unless asked. If someone asks you something, answer conversationally.\
"""


# ---------------------------------------------------------------------------
# Built-in realistic meeting transcript
# ---------------------------------------------------------------------------

def _line(minute: int, speaker: str, text: str, delay: float = 0) -> MeetingLine:
    return MeetingLine(speaker=speaker, text=text, minute=minute, delay_seconds=delay)


def generate_realistic_meeting() -> RealisticMeeting:
    """Generate a realistic, messy meeting transcript."""

    lines = []

    # --- Min 0-5: Joining, small talk, waiting for people ---
    lines.extend([
        _line(0, "Alice", "Hey hey, can you guys hear me OK? Last time my audio was all messed up."),
        _line(0, "Bob", "Yep, coming through fine. What's up Alice."),
        _line(0, "Carol", "Hang on, hang on, I'm getting coffee, one second."),
        _line(1, "Alice", "No rush. Bob, how was the weekend?"),
        _line(1, "Bob", "Oh it was good. Took the kids to that trampoline place, you know the one by the mall? SkyZone or whatever it's called. They went nuts."),
        _line(1, "Alice", "Oh nice, I keep meaning to take mine there."),
        _line(2, "David", "Hey, sorry, sorry, my last call went way over."),
        _line(2, "Alice", "You're fine. Carol, you back?"),
        _line(2, "Carol", "Yep, I'm here, let's do it."),
        _line(2, "Alice", "OK so I don't really have a formal agenda today, so let's just kind of go around. Bob, you wanna kick things off?"),
    ])

    # --- Min 3-10: Engineering update ---
    lines.extend([
        _line(3, "Bob", "Yeah sure. So, big news, we got the new search backend out on Friday, finally."),
        _line(3, "Alice", "Oh right right right, how'd it go?"),
        _line(3, "Bob", "Uh, pretty smooth honestly. We did have this one thing where the Elasticsearch cluster, it ran out of heap space at like three in the morning Saturday, but David was on call and caught it."),
        _line(4, "David", "Yeah, I just bumped the heap to thirty two gigs and it was fine after that."),
        _line(4, "Bob", "But the good news is latency is way way down. Like, before we were sitting at about six hundred milliseconds at the ninety-fifth percentile and now it's down to one forty."),
        _line(4, "Carol", "Wait. One forty? That's like, really good."),
        _line(5, "Bob", "Yeah, I mean the reindex took like nine hours which was way longer than we thought, but whatever, the numbers speak for themselves."),
        _line(5, "Alice", "So what's left, like what still needs to happen after the launch?"),
        _line(5, "Bob", "OK so there's this thing, the autocomplete, it's still pulling from the old index. And, uh, let me think who's on that. Yeah, Tomas, Tomas Kovac, he's supposed to have that done by Wednesday."),
        _line(6, "David", "Wait, Tomas? He was doing the rate limiter stuff too."),
        _line(6, "Bob", "Yeah that got pushed. Autocomplete is more important right now because people are literally seeing stale results in production."),
        _line(6, "Alice", "OK so Tomas has the autocomplete fix, Wednesday, got it."),
        _line(7, "Bob", "Oh and also, we gotta make a call on caching. I've been going back and forth, like, Redis versus Memcached, and I think at this point I'm just gonna say Redis because we can use it for sessions too and we already have the cluster."),
        _line(7, "David", "Yeah, Redis makes sense. One less thing to manage."),
        _line(8, "Carol", "Hey, sorry, can I just jump in real quick? Does the search change break anything on mobile? I'm getting some weird bug reports."),
        _line(8, "Bob", "It shouldn't, the API's the same. What kind of bugs are you seeing?"),
        _line(8, "Carol", "I don't know, let me just, I'll Slack you after this. Might be unrelated."),
        _line(9, "Alice", "OK, moving on. Carol, what's going on with you?"),
    ])

    # --- Min 9-18: Design/product update ---
    lines.extend([
        _line(9, "Carol", "OK so, the dashboard redesign. Basically we're doing cards instead of the table layout."),
        _line(10, "Alice", "And what did the user tests say?"),
        _line(10, "Carol", "It was mixed, honestly. Like, the power users hated it, they want their dense table view back. But the newer users really liked the cards, said it was way easier to understand."),
        _line(10, "Bob", "Could we just do both? Like a toggle?"),
        _line(11, "Carol", "That's kind of what I was thinking. Like, cards by default, but you can flip it to table view. It's more work though."),
        _line(11, "Bob", "How much more?"),
        _line(11, "Carol", "Probably like an extra sprint. But honestly the table view needs to be rebuilt anyway with the new component library, so."),
        _line(12, "Alice", "Yeah let's do the toggle. We can't piss off the power users, they're the ones paying us."),
        _line(12, "David", "Agreed, those are like our best customers."),
        _line(12, "Carol", "OK, cool, I'll plan for both. Oh, random thing, did anyone see Raj's Figma comments? He had like a whole rant about the color scheme."),
        _line(13, "Alice", "Yeah I saw. Some of it's fair, but the orange is staying. Marketing already signed off on it for the rebrand."),
        _line(13, "Carol", "Yeah, I told him. He's not thrilled but, whatever."),
        _line(14, "Alice", "What about mobile?"),
        _line(14, "Carol", "So that's the tricky part. Cards actually look great on mobile, but the table view is like, completely unusable on anything smaller than an iPad. So on mobile it'd just be cards no matter what."),
        _line(15, "Alice", "That makes sense. Timeline?"),
        _line(15, "Carol", "If we start next sprint, uh, cards in three weeks, and then the toggle adds like two more weeks on top of that. So five weeks total for the whole thing."),
        _line(16, "Alice", "Five weeks, cool, let's lock that in."),
        _line(16, "David", "Oh wait, sorry, are we changing the API at all? Because I need to know for the caching stuff."),
        _line(17, "Carol", "No no, same data, it's just the frontend, the rendering part."),
        _line(17, "David", "OK, good, no work for me then."),
        _line(17, "Alice", "Cool. David, what's happening on your end?"),
    ])

    # --- Min 17-28: Infrastructure, budget, incident ---
    lines.extend([
        _line(18, "David", "So, first thing, the cloud bill came in for February and it's, uh, it's not great."),
        _line(18, "Alice", "How not great?"),
        _line(18, "David", "Sixty three thousand."),
        _line(18, "Bob", "Wait, sixty three? We were at what, fifty one?"),
        _line(19, "David", "Yeah, fifty one last month. So couple things. The GPU instances for the ML stuff are expensive, and then somebody left three staging environments running over the weekend which was like four grand by itself."),
        _line(19, "Alice", "OK we need to automate killing those."),
        _line(20, "David", "Already doing it. I'm setting up a Lambda that just nukes any staging env that's been sitting there idle for more than four hours."),
        _line(20, "Bob", "And the GPU costs? Like, those aren't going away."),
        _line(20, "David", "No, but so I talked to our AWS rep, Vanessa, Vanessa Park, and she's putting together this proposal for reserved instances. She thinks we can save about thirty percent."),
        _line(21, "Alice", "Thirty percent off GPU specifically?"),
        _line(21, "David", "Off total compute. So, ballpark, we'd go from sixty three down to like forty five, forty six."),
        _line(21, "Alice", "OK that's significant. When do we get the proposal?"),
        _line(22, "David", "She said end of this week. Oh, uh, different topic, but we had that incident Thursday night."),
        _line(22, "Alice", "The database thing?"),
        _line(22, "David", "Yeah so basically the connection pool on the main Postgres instance, it got completely exhausted. The app kept opening connections and never closing them. Took us like forty five minutes to track it down."),
        _line(23, "Bob", "Yeah, that was us. My team. We had a missing finally block in the transaction handler. Totally our fault."),
        _line(23, "David", "It's fixed now, but like, during those forty five minutes about twelve hundred users got errors. Error rate went up to eight percent."),
        _line(24, "Alice", "Should we do a post-mortem?"),
        _line(24, "David", "Yeah, definitely. The other thing is our alerting was too slow. PagerDuty didn't fire until twelve minutes in. That should be like two, three minutes tops."),
        _line(24, "Bob", "That's because the threshold was set at five percent. I'll drop it to two."),
        _line(25, "Alice", "Good. David, can you own the post-mortem? Try to get it done by Friday."),
        _line(25, "David", "Yeah, I'll set up the review for Monday."),
        _line(26, "Alice", "Anything else infra-wise?"),
        _line(26, "David", "One more thing. Redis upgrade. We're on version six and there's this memory fragmentation bug that keeps causing GC pauses. Seven fixes it."),
        _line(27, "Bob", "When do you wanna do it?"),
        _line(27, "David", "Saturday, maintenance window. Rolling upgrade, twenty minutes, zero downtime if all goes well."),
        _line(27, "Alice", "OK, just make sure you send the maintenance notice to customers by Thursday."),
        _line(28, "David", "Will do."),
    ])

    # --- Min 28-38: Hiring, customer stuff, tangents ---
    lines.extend([
        _line(28, "Alice", "OK, hiring. We've got two open reqs, senior backend and the DevOps person."),
        _line(29, "Bob", "So for backend, I talked to this guy last week, uh, what's his name, Mateo, Mateo Ruiz. He's at Datadog right now. Really sharp, like eight years of Go, really solid system design."),
        _line(29, "Alice", "How'd the technical go?"),
        _line(29, "Bob", "He crushed it. Like, best system design interview I've seen in a while. Only thing is comp, he's senior staff at Datadog so he's probably not cheap."),
        _line(30, "Alice", "What's our budget?"),
        _line(30, "Bob", "One ninety to two twenty."),
        _line(30, "Alice", "That should work. Let's get him into finals. Can you set that up this week?"),
        _line(30, "Bob", "Yep, I'll ping him today."),
        _line(31, "David", "DevOps is rough. The last three people I talked to were all way too junior."),
        _line(31, "Alice", "Have you tried the DevOps subreddit?"),
        _line(31, "David", "Actually no. That's a good idea, I'll post there."),
        _line(32, "Carol", "Oh hey, totally random, did anyone see Prashant's message in Slack? About the demo Thursday?"),
        _line(32, "Alice", "The Meridian Health thing?"),
        _line(32, "Carol", "Yeah. They wanna see the reporting module apparently. Prashant's asking if we can show the export feature even though it's not totally done."),
        _line(33, "Bob", "I mean, it works, it's just slow with big datasets. If the demo data is small it'll be fine."),
        _line(33, "Alice", "Yeah, let's use the demo environment. Carol, can you make sure the data looks decent in there?"),
        _line(33, "Carol", "Yeah I'll handle it."),
        _line(34, "Alice", "This is a big deal by the way, guys. Meridian is like a two hundred K a year opportunity."),
        _line(34, "Bob", "Seriously?"),
        _line(34, "Alice", "Yeah, enterprise healthcare. But they need SOC 2 which is why it's been dragging."),
        _line(35, "David", "We have Type I already. Type II audit is September."),
        _line(35, "Alice", "Right but they want Type II. Prashant's telling them we'll have it Q1 next year."),
        _line(36, "Carol", "Oh that reminds me. Zenith Analytics has been complaining about the dashboard being slow."),
        _line(36, "Bob", "That's probably the search thing. The new backend should help."),
        _line(36, "Carol", "Yeah, I'll check back with them after Wednesday once Tomas gets the autocomplete fix in."),
        _line(37, "Alice", "Cool. OK what else, oh, the offsite. Anyone look into venues?"),
    ])

    # --- Min 38-48: Offsite, roadmap, Node upgrade ---
    lines.extend([
        _line(38, "Carol", "Yeah so I checked out a bunch of places. The best one I found is this place called Summit Lodge, it's in Tahoe. Four hundred a night per person, and that includes food and a meeting room."),
        _line(39, "Alice", "How many people total?"),
        _line(39, "Carol", "Twenty three, whole company. Three nights."),
        _line(39, "David", "So that's like, what, twenty seven thousand six hundred bucks?"),
        _line(40, "Alice", "Yeah roughly. Dates?"),
        _line(40, "Carol", "I was thinking week of June sixteenth. It's after the SOC 2 crunch and before everyone starts taking summer vacation."),
        _line(40, "Alice", "Works for me. Anyone have a conflict?"),
        _line(41, "Bob", "Lemme check. No, I'm good."),
        _line(41, "David", "Same, I'm fine."),
        _line(41, "Alice", "OK Carol, book it. Summit Lodge, June sixteenth, twenty three people."),
        _line(42, "Carol", "Done. I'll send the invite after this."),
        _line(42, "Alice", "OK, roadmap. So I talked to the advisory board last week and the number one thing is still the API marketplace."),
        _line(43, "Bob", "That's been number one for like three quarters. We keep saying we'll do it and then we don't."),
        _line(43, "Alice", "I know. But I think this time we actually have to do it. It comes up in literally every QBR."),
        _line(43, "Carol", "What are we talking about exactly? Like a Zapier thing or more of a developer portal?"),
        _line(44, "Alice", "More like a developer portal. Third parties can list their integrations, customers browse and install them. Kind of like the Slack app directory."),
        _line(44, "Bob", "I mean that's a massive project. We're talking multiple quarters."),
        _line(44, "Alice", "Right, but I wanna figure out the MVP. Bob, can you and your team do a spike this sprint? Just figure out what the minimum version looks like?"),
        _line(45, "Bob", "Yeah, I can have something by end of next week."),
        _line(45, "David", "There's a whole infra side to this too. Multi-tenant execution, sandboxing, all that."),
        _line(45, "Alice", "I know. David, work with Bob on it."),
        _line(46, "Bob", "Oh wait, totally unrelated, can we talk about the Node upgrade real quick? We're still on eighteen and it goes end of life next month."),
        _line(46, "David", "Just go to twenty two, that's the LTS."),
        _line(46, "Bob", "Yeah that's what I'm thinking but it's gonna break stuff. At least three packages need major version bumps."),
        _line(47, "David", "Which ones?"),
        _line(47, "Bob", "Mongo driver, Winston, and that XML parser for the SAML flow."),
        _line(47, "Alice", "How long?"),
        _line(47, "Bob", "Like a week if someone's dedicated to it. Two weeks if we're being thorough."),
        _line(48, "Alice", "Do two weeks. Start after the autocomplete thing ships."),
        _line(48, "Bob", "I'll put Tomas on it, he'll be free after Wednesday."),
    ])

    # --- Min 48-58: Wrap-up, misc items ---
    lines.extend([
        _line(48, "Alice", "Oh, David, what happened with the logging tool evaluation?"),
        _line(49, "David", "Right, yeah, so we're down to two. Datadog Logs and Mezmo. Mezmo is way cheaper, like four thousand a month versus eleven thousand for Datadog. But Datadog has the better alerting."),
        _line(49, "Alice", "What would you go with?"),
        _line(49, "David", "Honestly? Mezmo. That's eighty four thousand a year we'd save. And we can just use PagerDuty for the alerting part."),
        _line(50, "Alice", "Bob?"),
        _line(50, "Bob", "I used Mezmo before, at my last job. It's fine. Takes a bit to learn the query language but it does what you need."),
        _line(50, "Alice", "OK, let's go Mezmo. David, get procurement started."),
        _line(51, "David", "On it."),
        _line(51, "Carol", "Oh hey, quick thing. Newsletter goes out Friday and I need like two sentences about the search improvement. Bob, can you write something?"),
        _line(51, "Bob", "Uh, yeah, sure. I'll send it over tomorrow."),
        _line(52, "Carol", "Thanks. Also, heads up, NPS dropped. We were at forty two last month, now we're at thirty seven. Main complaint is the mobile app being slow."),
        _line(52, "Alice", "Thirty seven. That's not good."),
        _line(52, "Carol", "Yeah. Mobile team knows but they're buried with the dashboard responsive stuff."),
        _line(53, "Alice", "Could we get a contractor?"),
        _line(53, "Carol", "Maybe, yeah. I actually know someone, really good React Native person. Anika, something. I'll dig up her info."),
        _line(53, "Alice", "Yeah send it to me. If she's good we'll bring her on for like three months."),
        _line(54, "David", "Oh, last thing. SSL certs for the API domain expire April third. That's twelve days. I'll renew them this week."),
        _line(54, "Bob", "Please. We do not need another one of those surprise cert expirations."),
        _line(55, "Alice", "OK, are we done?"),
        _line(55, "Bob", "I think so."),
        _line(55, "Carol", "Wait, is the design review still Wednesday at two? For the onboarding flow?"),
        _line(56, "Alice", "Yep. You're presenting, right?"),
        _line(56, "Carol", "Yeah, I'll have the prototype done by then."),
        _line(56, "David", "Can I skip it? I've got the AWS training thing."),
        _line(56, "Alice", "Yeah that's fine, Carol'll catch you up."),
        _line(57, "Alice", "Alright, good meeting everyone. Have a good week."),
        _line(57, "Bob", "Later."),
        _line(57, "Carol", "Bye."),
        _line(57, "David", "See ya."),
    ])

    # --- Mid-meeting questions (natural, casual) ---
    mid_questions = [
        MidMeetingQuestion(
            trigger_after_minute=15,
            question="Hey Otto, what was that search latency number Bob mentioned earlier?",
            ground_truth="p95 search latency went from 600ms to 140ms",
        ),
        MidMeetingQuestion(
            trigger_after_minute=30,
            question="Otto, who's the backend candidate Bob was talking about?",
            ground_truth="Mateo Ruiz from Datadog, 8 years Go experience",
        ),
        MidMeetingQuestion(
            trigger_after_minute=45,
            question="What was the cloud bill number David mentioned?",
            ground_truth="$63,000, up from $51,000 last month",
        ),
    ]

    # --- Post-meeting questions (what a real user would ask) ---
    post_questions = [
        # Action items — the most common post-meeting ask
        PostMeetingQuestion(
            question_id="pm_01",
            question="What are the main action items from this meeting?",
            ground_truth="Tomas: autocomplete fix by Wednesday. David: post-mortem doc by Friday, Redis upgrade Saturday, maintenance notification by Thursday, book Mezmo. Bob: schedule Mateo final round, write newsletter blurb by tomorrow, API marketplace spike by end of next week. Carol: book Summit Lodge, prep demo data, follow up with Zenith Thursday, design review prototype by Wednesday.",
            category="action_item",
            difficulty="hard",
            source_minute=0,  # spans entire meeting
        ),
        # Specific decisions
        PostMeetingQuestion(
            question_id="pm_02",
            question="What did we decide about the caching strategy?",
            ground_truth="Going with Redis over Memcached because they can also use it for the session store and already have a cluster running.",
            category="decision",
            difficulty="medium",
            source_minute=7,
        ),
        PostMeetingQuestion(
            question_id="pm_03",
            question="What's the plan for the dashboard redesign?",
            ground_truth="Card-based layout by default with a toggle for table view. Cards-only on mobile. Three weeks for cards, five weeks total with table toggle.",
            category="decision",
            difficulty="medium",
            source_minute=15,
        ),
        # Numbers buried in conversation
        PostMeetingQuestion(
            question_id="pm_04",
            question="How much is the company offsite going to cost roughly?",
            ground_truth="About $27,600 (23 people x $400/night x 3 nights) at Summit Lodge in Lake Tahoe.",
            category="detail",
            difficulty="hard",
            source_minute=39,
        ),
        PostMeetingQuestion(
            question_id="pm_05",
            question="What's the deal with the Meridian Health opportunity?",
            ground_truth="$200K ARR enterprise healthcare deal. They want SOC 2 Type II (audit starts September, expect by Q1 next year). Demo on Thursday — they want to see reporting/export module. Prashant is managing the account.",
            category="detail",
            difficulty="hard",
            source_minute=34,
        ),
        # Inference questions — connecting dots
        PostMeetingQuestion(
            question_id="pm_06",
            question="Is Tomas going to be overloaded? What's he responsible for?",
            ground_truth="Tomas has: autocomplete fix (due Wednesday), then the Node.js upgrade to v22 (two weeks). The rate limiter work got pushed to make room. He should be OK since they're sequential.",
            category="inference",
            difficulty="hard",
            source_minute=6,
        ),
        PostMeetingQuestion(
            question_id="pm_07",
            question="What's happening with the database incident? Is it resolved?",
            ground_truth="The connection pool exhaustion bug is fixed (missing finally block in transaction handler). But post-mortem still needed (David owns, due Friday, review meeting Monday). Alert threshold being lowered from 5% to 2%. ~1200 users affected, 45 min outage, PagerDuty was 12 min late.",
            category="inference",
            difficulty="medium",
            source_minute=23,
        ),
        # Ambiguous / partial questions
        PostMeetingQuestion(
            question_id="pm_08",
            question="What was that thing about the color scheme Carol mentioned?",
            ground_truth="Raj left Figma comments with strong opinions about the color scheme. The orange accent is staying because marketing approved it for the rebrand. Carol told Raj and he's not happy.",
            category="ambiguous",
            difficulty="medium",
            source_minute=13,
        ),
        PostMeetingQuestion(
            question_id="pm_09",
            question="Who do I talk to about the AWS bill?",
            ground_truth="David is handling it. Their AWS rep is Vanessa Park, she's putting together a reserved instances proposal by end of this week that could save ~30% (from $63K to ~$45-46K/month).",
            category="ambiguous",
            difficulty="medium",
            source_minute=21,
        ),
        # Easy recall
        PostMeetingQuestion(
            question_id="pm_10",
            question="When and where is the company offsite?",
            ground_truth="Week of June 16th, Summit Lodge in Lake Tahoe.",
            category="detail",
            difficulty="easy",
            source_minute=40,
        ),
        PostMeetingQuestion(
            question_id="pm_11",
            question="Which log aggregation tool are we going with?",
            ground_truth="Mezmo over Datadog Logs. $4K/month vs $11K/month — saves $84K/year. David starting procurement.",
            category="decision",
            difficulty="easy",
            source_minute=49,
        ),
        PostMeetingQuestion(
            question_id="pm_12",
            question="What was the NPS score update?",
            ground_truth="Dropped from 42 to 37 last month. Biggest complaint is mobile app performance. Considering hiring a React Native contractor (Anika).",
            category="detail",
            difficulty="medium",
            source_minute=52,
        ),
    ]

    # --- Hallucination probes ---
    hallucination_probes = [
        HallucinationProbe("hp_01", "What did we decide about the pricing changes?"),
        HallucinationProbe("hp_02", "Who's replacing Carol on the design team?"),
        HallucinationProbe("hp_03", "What was the decision about moving to microservices?"),
        HallucinationProbe("hp_04", "When is the product launch event?"),
    ]

    return RealisticMeeting(
        title="Weekly Team Sync — Engineering, Design, Ops",
        lines=lines,
        mid_meeting_questions=mid_questions,
        post_meeting_questions=post_questions,
        hallucination_probes=hallucination_probes,
        duration_minutes=58,
    )


# ---------------------------------------------------------------------------
# External transcript loader
# ---------------------------------------------------------------------------

def load_external_transcript(
    transcript_path: str,
    questions_path: str | None = None,
) -> RealisticMeeting:
    """Load a meeting from external files.

    transcript_path: Text file or JSON file with meeting lines.

    Supports formats:
    1. Simple text (one line per turn):
       [Speaker]: text
       Alice: Hello everyone
       Bob: Hey, how's it going

    2. JSON array:
       [{"speaker": "Alice", "text": "Hello", "minute": 0}, ...]

    questions_path: Optional JSON file with post-meeting questions:
       [{"question_id": "q1", "question": "...", "ground_truth": "...", ...}]
    """
    path = Path(transcript_path)
    lines: list[MeetingLine] = []

    if path.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        for item in data:
            lines.append(MeetingLine(
                speaker=item.get("speaker", "Unknown"),
                text=item["text"],
                minute=item.get("minute", 0),
                delay_seconds=item.get("delay_seconds", 0),
            ))
    else:
        # Plain text format
        minute = 0
        with open(path) as f:
            for line_text in f:
                line_text = line_text.strip()
                if not line_text:
                    minute += 1  # blank line = rough minute boundary
                    continue
                if ":" in line_text:
                    speaker, text = line_text.split(":", 1)
                    # Handle [Speaker] format
                    speaker = speaker.strip().strip("[]")
                    lines.append(MeetingLine(
                        speaker=speaker, text=text.strip(), minute=minute,
                    ))
                else:
                    lines.append(MeetingLine(
                        speaker="Unknown", text=line_text, minute=minute,
                    ))

    # Load questions if provided
    post_questions: list[PostMeetingQuestion] = []
    if questions_path:
        with open(questions_path) as f:
            q_data = json.load(f)
        for q in q_data:
            post_questions.append(PostMeetingQuestion(
                question_id=q["question_id"],
                question=q["question"],
                ground_truth=q["ground_truth"],
                category=q.get("category", "detail"),
                difficulty=q.get("difficulty", "medium"),
                source_minute=q.get("source_minute", 0),
            ))

    duration = max((l.minute for l in lines), default=60)

    return RealisticMeeting(
        title=f"External Transcript: {path.name}",
        lines=lines,
        mid_meeting_questions=[],
        post_meeting_questions=post_questions,
        hallucination_probes=[],
        duration_minutes=duration,
    )
