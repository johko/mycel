-- Office of the Bursar — seed for the SQLite connector backend.
--
-- The bursar's data is genuinely tabular (payroll, accounts, grant ledger), so
-- this connector exposes it as a database the agent queries with SQL rather
-- than as flat records. Every business table carries a `source` column so the
-- OBLIGE egress policy can attach attribution to anything derived from a row.

CREATE TABLE payroll (
    id          TEXT PRIMARY KEY,
    period      TEXT,
    avg_research_staff  INTEGER,
    avg_support_staff   INTEGER,
    note        TEXT,
    source      TEXT
);

INSERT INTO payroll VALUES
    ('BUR-STAFF-2020-2024', '2020-2024', 64, 25,
     'Headcount funded through payroll; differs slightly from the Archivists'' staffing history, which counts all affiliated researchers.',
     'MICE Bursar Payroll Summary 2020-2024');

CREATE TABLE energy_accounts (
    id          TEXT PRIMARY KEY,
    period      TEXT,
    energy_spend_gp     INTEGER,
    estimated_total_kwh INTEGER,
    note        TEXT,
    source      TEXT
);

INSERT INTO energy_accounts VALUES
    ('BUR-ENERGY-SPEND-2020-2024', '2020-2024', 1240000, 3200000,
     'Consumption estimated from energy spend at contracted tariffs; an accounting estimate, not a meter reading.',
     'MICE Bursar Energy Accounts 2020-2024');

CREATE TABLE programs (
    id          TEXT PRIMARY KEY,
    period      TEXT,
    programs_launched   INTEGER,
    note        TEXT,
    source      TEXT
);

INSERT INTO programs VALUES
    ('BUR-PROGRAMS', '2020-2024', 2,
     'Two major experimental programs funded: the 2022 flux research program and the 2024 second experimental wing.',
     'MICE Bursar Grant Ledger');

CREATE TABLE assessments (
    id          TEXT PRIMARY KEY,
    claim       TEXT,
    assessment  INTEGER,  -- 1 = affirmed
    source      TEXT
);

INSERT INTO assessments VALUES
    ('BUR-DRIVER',
     'Campus energy consumption growth from 2020 is driven primarily by research lab expansion',
     1,
     'MICE Bursar Budget Commentary 2024');
