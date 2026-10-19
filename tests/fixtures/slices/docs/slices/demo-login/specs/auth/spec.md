## ADDED Requirements


### Requirement: AC-1 Valid credentials open a session
The system SHALL open a session when the email and password match an account.
Serves: US-1

#### Scenario: AC-1.1 Correct password
- GIVEN a registered customer on the sign-in page
- WHEN they submit the right email and password
- THEN they land on their saved work

#### Scenario: AC-1.2 Narrow screen
- GIVEN a 390 px wide viewport
- WHEN the sign-in page loads
- THEN the form is fully visible without sideways scrolling

### Requirement: AC-2 Failures are explained
The system MUST show a plain-language reason when sign-in fails.
Serves: US-1, US-2

#### Scenario: AC-2.1 Wrong password
- GIVEN a registered customer on the sign-in page
- WHEN they submit a wrong password
- THEN the page says the password is incorrect and keeps the email filled in
