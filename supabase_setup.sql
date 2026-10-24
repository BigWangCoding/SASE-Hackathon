-- ============================================================================
-- Sooner Buddies: Supabase setup
-- Run once: Supabase dashboard -> SQL Editor -> New query -> paste -> Run.
--
-- Design: the browser can only READ shared data and edit its own profile text
-- fields. Everything that changes stats (rewards, purchases, joins) goes through
-- the functions below, so the server decides what an action is worth.
-- ============================================================================

/* RESET (uncomment and run first if you want to start over)
drop view if exists public.leaderboard, public.clan_stats, public.party_list;
drop table if exists public.party_members, public.parties, public.raid_joins,
  public.items, public.events, public.profiles, public.clans cascade;
drop function if exists public.award(uuid,int,int), public.current_uid(),
  public.handle_new_user(), public.join_raid(int), public.start_session(int),
  public.complete_session(), public.cancel_session(), public.buy_item(text),
  public.join_party(bigint), public.create_party(text,text), public.join_clan(bigint),
  public.create_clan(text,text), public.leave_clan(), public.ensure_profile();
drop trigger if exists on_auth_user_created on auth.users;
*/

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table public.clans (
  id bigint generated always as identity primary key,
  name text not null check (char_length(name) between 3 and 40),
  tag text not null default 'Student organization' check (char_length(tag) <= 40),
  icon text not null default '🛡️',
  description text not null default '',
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);
create unique index clans_name_key on public.clans (lower(name));

create table public.events (
  id int primary key,
  title text not null,
  category text not null,
  month text not null,
  day text not null,
  time_text text not null,
  place text not null,
  reward int not null,
  xp int not null,
  description text not null
);

create table public.items (
  name text primary key,
  cat text not null,
  icon text not null,
  price int not null,
  description text not null,
  sort_order int not null default 0
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default 'Sooner Adventurer' check (char_length(display_name) between 1 and 30),
  major text not null default 'Undeclared' check (char_length(major) <= 60),
  gender text not null default 'Prefer not to say'
    check (gender in ('Prefer not to say','Male','Female','Non-binary')),
  classes text not null default '' check (char_length(classes) <= 200),
  cc int not null default 0,
  xp int not null default 0,
  level int not null default 1,
  study_hours numeric(10,3) not null default 0,
  sessions int not null default 0,
  raids int not null default 0,
  avatar text not null default '🧙',
  owned text[] not null default '{}',
  equipped text[] not null default '{}',
  clan_id bigint references public.clans(id) on delete set null,
  clan_cc int not null default 0,
  clan_xp int not null default 0,
  session_started timestamptz,
  session_minutes int,
  created_at timestamptz not null default now()
);

create table public.raid_joins (
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id int not null references public.events(id) on delete cascade,
  joined_at timestamptz not null default now(),
  primary key (user_id, event_id)
);

create table public.parties (
  id bigint generated always as identity primary key,
  name text not null check (char_length(name) between 3 and 40),
  type text not null default 'Study party',
  spot text not null check (char_length(spot) between 1 and 60),
  when_text text not null default 'Time to be arranged',
  max_members int not null default 5 check (max_members between 2 and 20),
  seed_members int not null default 0,   -- pretend members for the sample parties; set to 0 to remove
  icon text not null default '🛡️',
  description text not null default 'A new party led by you. Invite your fellow Sooners.',
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table public.party_members (
  party_id bigint not null references public.parties(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  joined_at timestamptz not null default now(),
  primary key (party_id, user_id)
);

-- ---------------------------------------------------------------------------
-- Row-level security and table privileges
-- ---------------------------------------------------------------------------
alter table public.profiles      enable row level security;
alter table public.events        enable row level security;
alter table public.items         enable row level security;
alter table public.raid_joins    enable row level security;
alter table public.clans         enable row level security;
alter table public.parties       enable row level security;
alter table public.party_members enable row level security;

revoke all on public.profiles, public.events, public.items, public.raid_joins,
  public.clans, public.parties, public.party_members from anon, authenticated;

-- profiles: read your own row; edit only the four text fields (never stats)
create policy "read own profile" on public.profiles
  for select to authenticated using (id = auth.uid());
create policy "edit own profile" on public.profiles
  for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
grant select on public.profiles to authenticated;
grant update (display_name, major, gender, classes) on public.profiles to authenticated;

-- catalogs: everyone signed in can read
create policy "read events" on public.events for select to authenticated using (true);
create policy "read items"  on public.items  for select to authenticated using (true);
grant select on public.events, public.items to authenticated;

-- raid joins: you can see your own
create policy "read own raid joins" on public.raid_joins
  for select to authenticated using (user_id = auth.uid());
grant select on public.raid_joins to authenticated;

-- clans, parties, party_members: no direct access; the views and functions below handle them

-- ---------------------------------------------------------------------------
-- Views (public leaderboard data only; email, gender and classes are never exposed)
-- Note: the Supabase dashboard may flag these as "security definer views".
-- That is intentional: it is how they read other users' rows safely.
-- ---------------------------------------------------------------------------
create view public.leaderboard as
select display_name, major, level, cc, raids, study_hours, (id = auth.uid()) as is_me
from public.profiles;

create view public.clan_stats as
select c.id, c.name, c.tag, c.icon, c.description,
       count(p.id)::int                                    as members,
       coalesce(sum(p.clan_cc), 0)::int                    as cc,
       coalesce(sum(p.clan_xp), 0)::int                    as xp,
       coalesce(sum(p.raids), 0)::int                      as raids,
       coalesce(sum(p.study_hours), 0)::numeric(10,1)      as study,
       (1 + coalesce(sum(p.clan_xp), 0) / 500)::int        as level,
       coalesce(bool_or(p.id = auth.uid()), false)         as is_member
from public.clans c
left join public.profiles p on p.clan_id = c.id
group by c.id;

create view public.party_list as
select p.id, p.name, p.type, p.spot, p.when_text, p.max_members, p.icon, p.description, p.created_at,
       (p.seed_members + (select count(*) from public.party_members m where m.party_id = p.id))::int as members,
       exists (select 1 from public.party_members m where m.party_id = p.id and m.user_id = auth.uid()) as joined,
       coalesce(p.created_by = auth.uid(), false) as is_leader
from public.parties p;

revoke all on public.leaderboard, public.clan_stats, public.party_list from anon, authenticated;
grant select on public.leaderboard, public.clan_stats, public.party_list to authenticated;

-- ---------------------------------------------------------------------------
-- Internal helpers
-- ---------------------------------------------------------------------------
create or replace function public.current_uid() returns uuid
language plpgsql stable as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Please sign in first'; end if;
  return uid;
end $$;

-- Adds CC/XP, handles level-ups (same rule as the demo: level * 250 XP per level),
-- and credits the clan contribution if the player is in a clan.
create or replace function public.award(p_user uuid, p_cc int, p_xp int) returns void
language plpgsql security definer set search_path = public as $$
declare r public.profiles;
begin
  select * into r from public.profiles where id = p_user for update;
  r.xp := r.xp + p_xp;
  r.cc := r.cc + p_cc;
  while r.xp >= r.level * 250 loop
    r.xp := r.xp - r.level * 250;
    r.level := r.level + 1;
  end loop;
  update public.profiles set
    cc = r.cc, xp = r.xp, level = r.level,
    clan_cc = clan_cc + case when clan_id is not null then p_cc else 0 end,
    clan_xp = clan_xp + case when clan_id is not null then p_xp else 0 end
  where id = p_user;
end $$;

-- Creates a profile row whenever someone signs up.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id,
          left(coalesce(nullif(btrim(new.raw_user_meta_data->>'display_name'), ''), 'Sooner Adventurer'), 30))
  on conflict (id) do nothing;
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Game actions (called from the browser with supabase.rpc)
-- ---------------------------------------------------------------------------
create or replace function public.ensure_profile() returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); me public.profiles;
begin
  insert into public.profiles (id) values (uid) on conflict (id) do nothing;
  select * into me from public.profiles where id = uid;
  return me;
end $$;

create or replace function public.join_raid(p_event int) returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); ev public.events; me public.profiles;
begin
  select * into ev from public.events where id = p_event;
  if not found then raise exception 'That event does not exist'; end if;
  if exists (select 1 from public.raid_joins where user_id = uid and event_id = p_event) then
    raise exception 'You already joined this raid';
  end if;
  insert into public.raid_joins (user_id, event_id) values (uid, p_event);
  update public.profiles set raids = raids + 1 where id = uid;
  perform public.award(uid, ev.reward, ev.xp);
  select * into me from public.profiles where id = uid;
  return me;
end $$;

-- Focus sessions: the server records the start time and refuses to pay out early.
-- (1 minute exists so a live audience can see a reward without waiting.)
create or replace function public.start_session(p_minutes int) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid();
begin
  if p_minutes not in (1, 25, 45, 60) then raise exception 'Unsupported session length'; end if;
  update public.profiles set session_started = now(), session_minutes = p_minutes where id = uid;
end $$;

create or replace function public.cancel_session() returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid();
begin
  update public.profiles set session_started = null, session_minutes = null where id = uid;
end $$;

create or replace function public.complete_session() returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); me public.profiles; mins int;
begin
  select * into me from public.profiles where id = uid for update;
  if me.session_started is null then raise exception 'No focus session is running'; end if;
  if now() < me.session_started + make_interval(secs => me.session_minutes * 60 - 5) then
    raise exception 'That session is not finished yet';
  end if;
  mins := me.session_minutes;
  update public.profiles set
    study_hours = study_hours + mins / 60.0,
    sessions = sessions + 1,
    session_started = null,
    session_minutes = null
  where id = uid;
  perform public.award(uid, mins, round(mins * 1.4)::int);
  select * into me from public.profiles where id = uid;
  return me;
end $$;

create or replace function public.buy_item(p_item text) returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); it public.items; me public.profiles;
begin
  select * into it from public.items where name = p_item;
  if not found then raise exception 'That item does not exist'; end if;
  select * into me from public.profiles where id = uid for update;
  if p_item = any (me.owned) then raise exception 'You already own this item'; end if;
  if me.cc < it.price then raise exception 'Not enough Crimson Crystals yet. Complete a quest to earn more.'; end if;
  update public.profiles set
    cc = cc - it.price,
    owned = owned || it.name,
    equipped = equipped || it.name,
    avatar = it.icon
  where id = uid;
  select * into me from public.profiles where id = uid;
  return me;
end $$;

create or replace function public.join_party(p_party bigint) returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); pt public.parties; me public.profiles;
begin
  select * into pt from public.parties where id = p_party for update;   -- lock so capacity is enforced
  if not found then raise exception 'That party does not exist'; end if;
  if exists (select 1 from public.party_members where party_id = p_party and user_id = uid) then
    raise exception 'You are already in this party';
  end if;
  if pt.seed_members + (select count(*) from public.party_members where party_id = p_party) >= pt.max_members then
    raise exception 'That party is full';
  end if;
  insert into public.party_members (party_id, user_id) values (p_party, uid);
  perform public.award(uid, 15, 20);
  select * into me from public.profiles where id = uid;
  return me;
end $$;

create or replace function public.create_party(p_name text, p_spot text) returns bigint
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); pid bigint;
begin
  p_name := btrim(coalesce(p_name, ''));
  p_spot := btrim(coalesce(p_spot, ''));
  if char_length(p_name) not between 3 and 40 then raise exception 'Party names need 3 to 40 characters'; end if;
  if char_length(p_spot) not between 1 and 60 then raise exception 'The meeting spot needs 1 to 60 characters'; end if;
  if (select count(*) from public.parties where created_by = uid) >= 3 then
    raise exception 'You can lead up to 3 parties';
  end if;
  insert into public.parties (name, spot, created_by) values (p_name, p_spot, uid) returning id into pid;
  insert into public.party_members (party_id, user_id) values (pid, uid);
  return pid;
end $$;

create or replace function public.join_clan(p_clan bigint) returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); me public.profiles;
begin
  if not exists (select 1 from public.clans where id = p_clan) then raise exception 'That clan does not exist'; end if;
  select * into me from public.profiles where id = uid for update;
  if me.clan_id is not null then raise exception 'Leave your current clan before joining another'; end if;
  update public.profiles set clan_id = p_clan, clan_cc = 0, clan_xp = 0 where id = uid;
  select * into me from public.profiles where id = uid;
  return me;
end $$;

create or replace function public.create_clan(p_name text, p_tag text) returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); me public.profiles; cid bigint;
begin
  p_name := btrim(coalesce(p_name, ''));
  p_tag  := btrim(coalesce(nullif(btrim(p_tag), ''), 'Student organization'));
  if char_length(p_name) not between 3 and 40 then raise exception 'Clan names need 3 to 40 characters'; end if;
  if char_length(p_tag) > 40 then raise exception 'Keep the organization type under 40 characters'; end if;
  select * into me from public.profiles where id = uid for update;
  if me.clan_id is not null then raise exception 'Leave your current clan before founding a new one'; end if;
  if exists (select 1 from public.clans where created_by = uid) then
    raise exception 'You can only found one clan';
  end if;
  begin
    insert into public.clans (name, tag, description, created_by)
    values (p_name, p_tag, 'A new clan founded by you. Invite fellow Sooners to grow together.', uid)
    returning id into cid;
  exception when unique_violation then
    raise exception 'That clan name is already taken';
  end;
  update public.profiles set clan_id = cid, clan_cc = 0, clan_xp = 0 where id = uid;
  select * into me from public.profiles where id = uid;
  return me;
end $$;

create or replace function public.leave_clan() returns public.profiles
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.current_uid(); me public.profiles;
begin
  update public.profiles set clan_id = null, clan_cc = 0, clan_xp = 0 where id = uid;
  select * into me from public.profiles where id = uid;
  return me;
end $$;

-- ---------------------------------------------------------------------------
-- Function permissions: only signed-in users may call the game actions;
-- the helpers cannot be called from the browser at all.
-- ---------------------------------------------------------------------------
revoke all on function public.current_uid()            from public, anon, authenticated;
revoke all on function public.award(uuid, int, int)    from public, anon, authenticated;
revoke all on function public.handle_new_user()        from public, anon, authenticated;

revoke all on function public.ensure_profile()         from public, anon;
revoke all on function public.join_raid(int)           from public, anon;
revoke all on function public.start_session(int)       from public, anon;
revoke all on function public.cancel_session()         from public, anon;
revoke all on function public.complete_session()       from public, anon;
revoke all on function public.buy_item(text)           from public, anon;
revoke all on function public.join_party(bigint)       from public, anon;
revoke all on function public.create_party(text, text) from public, anon;
revoke all on function public.join_clan(bigint)        from public, anon;
revoke all on function public.create_clan(text, text)  from public, anon;
revoke all on function public.leave_clan()             from public, anon;

grant execute on function public.ensure_profile()         to authenticated;
grant execute on function public.join_raid(int)           to authenticated;
grant execute on function public.start_session(int)       to authenticated;
grant execute on function public.cancel_session()         to authenticated;
grant execute on function public.complete_session()       to authenticated;
grant execute on function public.buy_item(text)           to authenticated;
grant execute on function public.join_party(bigint)       to authenticated;
grant execute on function public.create_party(text, text) to authenticated;
grant execute on function public.join_clan(bigint)        to authenticated;
grant execute on function public.create_clan(text, text)  to authenticated;
grant execute on function public.leave_clan()             to authenticated;

-- ---------------------------------------------------------------------------
-- Seed data (the sample content from the original prototype)
-- ---------------------------------------------------------------------------
insert into public.events (id, title, category, month, day, time_text, place, reward, xp, description) values
 (1,'OU Engineering Student Mixer','Social','OCT','25','5:30 PM','Devon Energy Hall',90,120,'Meet fellow engineers and build your campus network.'),
 (2,'Undergraduate Research Showcase','Academic','OCT','27','2:00 PM','Oklahoma Memorial Union',110,150,'Explore research projects and meet student researchers.'),
 (3,'Career Center Resume Lab','Career','OCT','28','11:00 AM','Student Union, Room 360',75,100,'Polish your resume with hands-on feedback.'),
 (4,'Sooner Wellness Walk','Wellness','OCT','29','4:00 PM','South Oval',60,80,'Take a break, meet people, and recharge.'),
 (5,'Math & Physics Study Jam','Academic','OCT','30','6:00 PM','Engineering Practice Facility',100,130,'Collaborative problem-solving with classmates.'),
 (6,'International Coffee Social','Social','NOV','02','10:00 AM','Oklahoma Memorial Union',70,90,'Coffee, conversation, and new connections.')
on conflict (id) do nothing;

insert into public.items (name, cat, icon, price, description, sort_order) values
 ('Crimson Flow','Hair','💇',180,'A bold new adventurer hairstyle.',1),
 ('Golden Crown','Hats','👑',420,'A crown worthy of a campus legend.',2),
 ('Sooner Jersey','Shirts','👕',260,'Classic crimson-and-gold game-day style.',3),
 ('Scholar Robe','Shirts','🥋',340,'For those who conquer every exam.',4),
 ('Explorer Trousers','Pants','👖',160,'Built for your next campus quest.',5),
 ('Golden Kicks','Shoes','👟',300,'Make every step legendary.',6),
 ('Crystal Pendant','Accessories','📿',220,'A little extra sparkle for your build.',7),
 ('Scholar Specs','Eyewear','🤓',190,'Intelligence stat: visually increased.',8),
 ('Raid Shield','Accessories','🛡️',500,'A symbol of your party dedication.',9),
 ('Crimson Cap','Hats','🧢',150,'Casual look, serious questing.',10),
 ('Pixel Shades','Eyewear','🕶️',240,'Rare style for a rising legend.',11),
 ('Campus Sneakers','Shoes','🥾',210,'Ready for a full day of adventures.',12)
on conflict (name) do nothing;

insert into public.clans (name, tag, icon, description) values
 ('Engineers Without Limits','Engineering club','⚙️','Build skills, solve problems, and support fellow engineers.'),
 ('Sooner Scholars Society','Academic organization','📚','A community built around study sessions and academic growth.'),
 ('Crimson Campus Collective','Student organization','🔴','Show up, meet people, and make the most of campus life.'),
 ('Women in STEM','Student organization','🔬','Grow together through mentorship and collaborative learning.'),
 ('Delta Study Society','Greek life · sample','🏛️','A Greek-life community that puts academics and friendship first.'),
 ('Sooner Outdoor Club','Campus club','⛰️','Find your people and explore campus and beyond.')
on conflict ((lower(name))) do nothing;

insert into public.parties (name, type, spot, when_text, max_members, seed_members, icon, description) values
 ('Statics Survival Squad','Study party','Bizzell Memorial Library','Today · 6:00 PM',5,3,'📐','Free-body diagrams, equilibrium, and exam prep.'),
 ('South Oval Social Crew','Raid party','South Oval','Tomorrow · 4:00 PM',6,4,'🌳','Head to campus events together and meet new Sooners.'),
 ('Late-Night Code Guild','Study party','Engineering Practice Facility','Tonight · 8:00 PM',4,2,'💻','Programming assignments and project accountability.');

-- make the API pick up the new tables and functions immediately
notify pgrst, 'reload schema';
