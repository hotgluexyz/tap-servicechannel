# tap-servicechannel

`tap-servicechannel` is a Singer tap for [ServiceChannel](https://servicechannel.com/), a facilities and service automation platform.

Built with the [Hotglue Singer SDK](https://github.com/hotgluexyz/HotglueSingerSDK) for Singer Taps.

## Installation

```bash
pip install tap-servicechannel
```

Or install directly from the repository:

```bash
pip install git+https://github.com/hotgluexyz/tap-servicechannel.git
```

## Configuration

### Accepted Config Options

| Setting         | Required | Description                                                                 |
|-----------------|----------|-----------------------------------------------------------------------------|
| `client_id`     | Yes      | ServiceChannel OAuth2 client ID (from App Registration)                     |
| `client_secret` | Yes      | ServiceChannel OAuth2 client secret                                         |
| `username`      | Yes      | ServiceChannel account username                                             |
| `password`      | Yes      | ServiceChannel account password                                             |
| `start_date`    | No       | The earliest record date to sync (ISO 8601 / datetime format)               |

Example `config.json`:

```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "username": "your_username",
  "password": "your_password",
  "start_date": "2024-01-01T00:00:00Z"
}
```

A full list of supported settings and capabilities for this tap is available by running:

```bash
tap-servicechannel --about
```

### Configure using environment variables

This Singer tap will automatically import any environment variables within the working directory's
`.env` if the `--config=ENV` is provided, such that config values will be considered if a matching
environment variable is set either in the terminal context or in the `.env` file.

### Source Authentication and Authorization

This tap uses OAuth2 resource owner password credentials. The `client_id` and `client_secret` are
sent as HTTP Basic auth, and the `username`/`password` are exchanged for a short-lived access token
(valid for ~10 minutes) that is automatically refreshed. Obtain OAuth credentials by registering an
application in the ServiceChannel [App Registration](https://developer.servicechannel.com/basics/general/app-registration/)
page. See the [Authentication guide](https://developer.servicechannel.com/basics/general/authentication/) for details.

## Supported Streams

| Stream        | Replication Key | Primary Key | Description                                                        |
|---------------|-----------------|-------------|-------------------------------------------------------------------|
| `invoices`    | `UpdatedDate`   | `Id`        | Invoices from the ServiceChannel OData API                        |
| `attachments` | _(none)_        | `Id`        | Work order attachments, fetched per invoice's `WoTrackingNumber`  |

The `invoices` stream reads from `https://api.servicechannel.com/odata/invoices` and paginates using
the OData `$top`/`$skip` parameters (the API caps the page size at 50 and returns an `@odata.nextLink`
while more pages remain). Incremental replication is performed with an OData `$filter` on `UpdatedDate`.

The `attachments` stream is a child of `invoices`. Each invoice exposes a `WoTrackingNumber`
identifying its work order, which is used to read
`https://api.servicechannel.com/v3/odata/workorders({WoTrackingNumber})/attachments`. Because
attachments are retrieved per work order, they are effectively refreshed for whichever invoices are
pulled in each run, so incremental coverage is driven by the parent `invoices` stream. Each attachment
record includes a `wo_tracking_number` field linking it back to its work order.

## Usage

You can easily run `tap-servicechannel` by itself or in a pipeline.

### Executing the Tap Directly

```bash
tap-servicechannel --version
tap-servicechannel --help
tap-servicechannel --config CONFIG --discover > ./catalog.json
tap-servicechannel --config CONFIG --catalog CATALOG > ./data.singer
```

## Developer Resources

### Initialize your Development Environment

```bash
pipx install poetry
poetry install
```

### Create and Run Tests

Create tests within the `tap_servicechannel/tests` subfolder and then run:

```bash
poetry run pytest
```

You can also test the `tap-servicechannel` CLI interface directly using `poetry run`:

```bash
poetry run tap-servicechannel --help
```
