drop table gameinfo;
drop table assassins;
drop table games;
drop table rules;
drop table config;

PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE gameinfo(id integer primary key, game_id integer not null, assassin_id integer not null, target_id integer, killer_id integer, kill_datetime timestamp, ranking integer, confirm_hash text, reporting_killer text);
CREATE TABLE assassins(id integer primary key, nickname text not null, firstname text, lastname text, password text, email_address text not null, picture_filename text, smack text, ranking integer, email_updates integer default 1, email_newgames integer default 1);
CREATE TABLE games(id integer primary key, start_datetime timestamp default current_timestamp, end_datetime timestamp, rule_id number, gametype number);
CREATE TABLE rules(id integer primary key, rules text, rulename text);
CREATE TABLE config(name text not null, value text);
COMMIT;

