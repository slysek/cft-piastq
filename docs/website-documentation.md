# cft-piastq

`cft-piastq` to biblioteka Pythona dla zespołu pracującego z PiastQ, Qiskit i
zarządzanym wykonywaniem zadań kwantowych. Pakiet importuje się jako
`cft_piastq` i porządkuje warstwę kliencką wokół trzech ścieżek:

- zadań obsługiwanych przez zarządzany dashboard,
- bezpośredniej pracy z lokalnym tokenem PCSS/AQT,
- lokalnego trybu testowego opartego o backend fake.

Biblioteka nie zastępuje Qiskita. Jej rolą jest konfiguracja klienta, wybór
trybu wykonania, komunikacja z dashboardem, serializacja obwodów i odtwarzanie
wyników w formacie zgodnym z Qiskitem.

W wersji `0.1.0` gotowy jest stabilny rdzeń: `PiastQClient`, backendy
uchwytowe, zarządzany `PiastQSampler`, `PiastQJob`, klient HTTP dashboardu, QPY,
rekonstrukcja wyników, statusy, błędy i redakcja sekretów. Warstwy samplera dla
trybów `direct` i `fake` są nadal kolejnym etapem.

## Dla kogo jest ta biblioteka

`cft-piastq` jest przeznaczone dla osób, które chcą pisać notebooki i skrypty
Qiskitowe bez przepisywania za każdym razem logiki wyboru środowiska.

Docelowy kontrakt biblioteki pozwala prowadzić ten sam eksperyment:

- przez dashboard, gdy dostępny jest zarządzany runner,
- lokalnie, gdy użytkownik ma token PCSS,
- w trybie fake, gdy celem jest test, demonstracja albo szybka walidacja
  przepływu danych.

Najważniejszy efekt: kod eksperymentu pozostaje blisko Qiskita, a logika
operacyjna trafia do jednej biblioteki.

## Instalacja

W repozytorium developerskim:

```powershell
python -m pip install -e .[dev]
```

Opcjonalne zależności są rozdzielone według trybu pracy:

```powershell
python -m pip install -e .[direct]
python -m pip install -e .[fake]
```

`direct` instaluje integracje potrzebne do ścieżki PCSS/AQT. `fake` instaluje
zależności potrzebne do lokalnego backendu symulacyjnego.

## Szybki start

Najprostszy punkt wejścia to `PiastQClient`. Klient czyta konfigurację z
argumentów konstruktora albo ze zmiennych środowiskowych, wybiera tryb pracy i
wystawia uchwyt `backend`.

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(
    owner="szymo",
    mode="managed",
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
    verbose=False,
)

sampler = PiastQSampler(
    client.backend,
    options={"cft_job_name": "Bell smoke test"},
)

job = sampler.run(circuits=[circuit], shots=200)
result = job.result()
counts = job.counts(num_bits=2)
```

Dla trybu `managed` lokalny token PCSS nie jest wymagany. Biblioteka sprawdza
zdrowie zarządzanego runnera po stronie dashboardu i dopiero wtedy wybiera
backend `managed`.

Jeżeli zadanie ma przejść przez dashboard, używaj `PiastQSampler`. Surowy
`qiskit_aqt_provider.primitives.AQTSampler` jest samplerem providera AQT i nie
zna endpointów zarządzanego dashboardu.

## Tryby wykonania

`PiastQClient` obsługuje cztery wartości `mode`.

| Tryb | Zachowanie |
| --- | --- |
| `managed` | Wymaga adresu dashboard API. Klient wykonuje healthcheck runnera i wybiera backend zarządzany. |
| `direct` | Wymaga lokalnego tokenu PCSS. Klient wybiera backend bezpośredni i nie potrzebuje dashboardu. |
| `fake` | Zwraca lokalny backend fake. Może opcjonalnie pobrać model szumu z dashboardu. |
| `auto` | Próbuje użyć `managed`, jeżeli dashboard jest skonfigurowany i zdrowy. Gdy dashboard jest niedostępny, przechodzi na `direct` tylko wtedy, gdy dostępny jest lokalny token PCSS. |

Błąd autoryzacji dashboardu (`401` albo `403`) jest traktowany jako błąd
twardy. W takim przypadku `auto` nie przechodzi po cichu na tryb `direct`,
ponieważ mogłoby to ukryć problem z uprawnieniami.

## Konfiguracja

Konfigurację można przekazać jawnie:

```python
client = PiastQClient(
    mode="auto",
    owner="szymo",
    token="local-pcss-token",
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
    registry_path="jobs.sqlite3",
    verbose=False,
)
```

Albo przez zmienne środowiskowe:

| Zmienna | Znaczenie |
| --- | --- |
| `CFT_PIASTQ_OWNER` | Właściciel joba widoczny w dashboardzie. Można też przekazać `owner=` w konstruktorze. |
| `CFT_PIASTQ_MODE` | `auto`, `managed`, `direct` albo `fake`. Domyślnie `auto`. |
| `PCSS_TOKEN` | Lokalny token PCSS dla trybu `direct`. |
| `PCSS_QAPI_TOKEN` | Alternatywna nazwa lokalnego tokenu PCSS. |
| `CFT_PIASTQ_DASHBOARD_API_URL` | Bazowy adres API dashboardu. |
| `CFT_PIASTQ_DASHBOARD_API_KEY` | Klucz API dashboardu. |
| `CFT_PIASTQ_VERBOSE` | Wartość logiczna, np. `true`, `false`, `1`, `0`, `yes`, `no`. |
| `CFT_PIASTQ_REGISTRY_PATH` | Ścieżka lokalnego rejestru zadań dla trybu direct. |

Argumenty konstruktora mają pierwszeństwo przed zmiennymi środowiskowymi.

## Managed dashboard

Tryb `managed` służy do pracy z runnerem po stronie dashboardu. Klient tworzy
`DashboardClient`, wykonuje `GET /api/runner/health` i dopiero wtedy uznaje
backend za dostępny.

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(
    owner="szymo",
    mode="managed",
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
    verbose=False,
)

backend = client.backend
dashboard = client.dashboard_client

sampler = PiastQSampler(
    backend,
    options={
        "with_progress_bar": False,
        "cft_job_name": "Bell smoke test",
        "cft_description": "2Q Bell test before RB run",
    },
)

job = sampler.run(circuits=[circuit], shots=200)
result = job.result()
counts = job.counts(num_bits=2)
```

W tym trybie biblioteka nie przesyła lokalnego tokenu PCSS do dashboardu.
Dashboard dostaje tylko klucz API dashboardu, jeżeli dana operacja go wymaga.
Opcje z prefiksem `cft_` trafiają do metadanych joba dashboardowego, a nie do
opcji providera.

## Tryb direct

Tryb `direct` jest przeznaczony do lokalnej ścieżki PCSS/AQT. W obecnej wersji
klient wybiera i zwraca backend uchwytowy dla tej ścieżki; pełne wykonywanie
zadań przez sampler należy do kolejnego etapu API.

Jeżeli token nie zostanie podany ani przez konstruktor, ani przez środowisko,
klient rzuci `DirectModeUnavailableError`.

```python
from cft_piastq import PiastQClient

client = PiastQClient(
    owner="szymo",
    mode="direct",
    token="local-pcss-token",
    verbose=False,
)

assert client.execution_mode == "direct"
assert client.backend.mode == "direct"
```

Token nie jest widoczny w reprezentacji tekstowej backendu, dzięki czemu
przypadkowy `repr(client.backend)` nie ujawnia sekretu w logach.

## Tryb fake

Tryb `fake` jest lekki i nadaje się do testów oraz lokalnego sprawdzania
przepływu aplikacji. W wersji `0.1.0` zwraca backend uchwytowy; pełna ścieżka
samplera fake jest częścią dalszego rozwoju.

```python
from cft_piastq import PiastQClient

client = PiastQClient(mode="fake", verbose=False)

assert client.backend.mode == "fake"
```

Można też włączyć model szumu pobierany z dashboardu:

```python
client = PiastQClient(
    owner="szymo",
    mode="fake",
    use_backend_noise=True,
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
    verbose=False,
)
```

Wtedy klient wywoła endpoint `GET /api/noise-model/latest` i zapisze odpowiedź
w backendzie fake.

## Klient HTTP dashboardu

Niższy poziom API jest dostępny przez `DashboardClient`.

```python
from cft_piastq.http import DashboardClient

dashboard = DashboardClient(
    "https://piastq-dashboard.example",
    api_key="dashboard-key",
)

health = dashboard.health()
job = dashboard.submit_job({"shots": 200})
fresh_status = dashboard.get_job(job["id"])
result = dashboard.get_result(job["id"])
dashboard.cancel_job(job["id"])
dashboard.close()
```

Obsługiwane endpointy:

| Metoda | Ścieżka | Metoda Pythona |
| --- | --- | --- |
| `GET` | `/api/runner/health` | `health()` |
| `POST` | `/api/runner/jobs` | `submit_job(payload)` |
| `GET` | `/api/runner/jobs/{id}` | `get_job(server_job_id)` |
| `GET` | `/api/runner/jobs/{id}/result` | `get_result(server_job_id)` |
| `POST` | `/api/runner/jobs/{id}/cancel` | `cancel_job(server_job_id)` |
| `GET` | `/api/noise-model/latest` | `get_noise_model()` |

`cancel_job()` wymaga klucza API dashboardu. Jeżeli go brakuje, biblioteka
zatrzymuje operację przed wysłaniem requestu.

## Serializacja obwodów Qiskit

Biblioteka używa QPY jako przenośnego formatu obwodów Qiskit. Payload jest
kodowany do base64, dzięki czemu można go przekazać jako JSON.

```python
from qiskit import QuantumCircuit
from cft_piastq.serialization import (
    circuit_metadata,
    circuit_to_qpy_base64,
    qpy_base64_to_circuit,
)

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

payload = circuit_to_qpy_base64(circuit)
restored = qpy_base64_to_circuit(payload)
metadata = circuit_metadata(circuit, index=0)
```

`circuit_metadata()` zwraca pola przydatne do dashboardu i audytu:

- indeks obwodu,
- nazwę obwodu,
- liczbę kubitów i bitów klasycznych,
- głębokość,
- zliczenia operacji,
- użyte kubity,
- użyte sprzężenia dwukubitowe.

Dostępne są też funkcje dla wielu obwodów:

```python
from cft_piastq.serialization import (
    circuits_to_qpy_base64,
    qpy_base64_to_circuits,
)

encoded = circuits_to_qpy_base64([circuit])
circuits = qpy_base64_to_circuits(encoded)
```

Pusty zestaw obwodów jest odrzucany, a błędy QPY/base64 są opakowane w publiczny
`PiastQError` z oczyszczonym komunikatem.

## Wyniki i estymowane counts

Dashboard może zwrócić wynik w JSON-ie, a biblioteka odtwarza z niego
`qiskit.primitives.SamplerResult`.

```python
from cft_piastq.results import sampler_result_from_json
from cft_piastq.counts import estimated_counts_from_result

payload = {
    "shots": 200,
    "quasi_dists": [{"0": 0.5, "3": 0.5}],
    "metadata": [{"circuit_index": 0, "circuit_name": "bell"}],
}

result = sampler_result_from_json(payload)
counts = estimated_counts_from_result(result, shots=200, num_bits=2)
```

`estimated_counts_from_result()` przelicza quasi-prawdopodobieństwa na wygodny
widok counts. To estymacja do prezentacji i analizy, a nie surowe counts
zwracane bezpośrednio przez provider.

## Statusy zadań

Provider i dashboard mogą używać różnych nazw statusów. `normalize_job_status()`
sprowadza je do wspólnego zestawu literałów.

```python
from cft_piastq.status import normalize_job_status

assert normalize_job_status("DONE") == "succeeded"
assert normalize_job_status("in-progress") == "running"
assert normalize_job_status("something-new") == "unknown"
```

Wspólne statusy:

- `queued`,
- `running`,
- `succeeded`,
- `failed`,
- `cancelled`,
- `stale`,
- `cancel_requested`,
- `unknown`.

## Błędy publiczne

Wszystkie publiczne wyjątki dziedziczą po `PiastQError`.

```python
from cft_piastq import (
    DashboardAuthError,
    DashboardUnavailableError,
    DirectModeUnavailableError,
    FakeBackendError,
    ManagedJobError,
    PiastQConfigurationError,
    PiastQError,
    PiastQTimeoutError,
)
```

Najczęstsze przypadki:

| Wyjątek | Kiedy występuje |
| --- | --- |
| `PiastQConfigurationError` | Niepełna albo nieprawidłowa konfiguracja klienta. |
| `DashboardUnavailableError` | Dashboard jest niedostępny albo runner jest wyłączony. |
| `DashboardAuthError` | Dashboard zwrócił `401` albo `403`. |
| `ManagedJobError` | Operacja na zadaniu zarządzanym nie powiodła się. |
| `DirectModeUnavailableError` | Tryb direct nie może ruszyć bez tokenu PCSS. |
| `FakeBackendError` | Tryb fake nie może pobrać lub użyć wymaganych danych. |
| `PiastQTimeoutError` | Oczekiwanie na zadanie przekroczyło limit czasu. |

## Bezpieczeństwo sekretów

`cft-piastq` ma wbudowane helpery do czyszczenia komunikatów z sekretów.
Dotyczy to tokenów PCSS, kluczy dashboardu, nagłówków `Authorization` oraz
długich ciągów wyglądających jak klucze API.

```python
from cft_piastq.security import redact_secrets, safe_error_message

message = redact_secrets(
    "PCSS_TOKEN=secret CFT_PIASTQ_DASHBOARD_API_KEY=dashboard-key job=bell"
)

assert "secret" not in message
assert "dashboard-key" not in message
assert "job=bell" in message
```

Ta sama redakcja jest stosowana w komunikatach błędów HTTP i QPY, aby logi były
użyteczne, ale nie ujawniały danych uwierzytelniających.

## Aktualny stan API

W wersji `0.1.0` gotowe i testowane są:

- wybór trybu przez `PiastQClient`,
- backendy uchwytowe dla `managed`, `direct` i `fake`,
- `PiastQSampler` dla trybu `managed`,
- `PiastQJob` z `job_id()`, `status()`, `result()`, `cancel()` i `counts()`,
- klient HTTP dashboardu,
- serializacja i deserializacja QPY,
- rekonstrukcja `SamplerResult` z JSON-a,
- estymowane counts z quasi-dystrybucji,
- normalizacja statusów,
- publiczna hierarchia błędów,
- redakcja sekretów.

`PiastQSampler` obsługuje obecnie backend zarządzany. Dla backendów `direct` i
`fake` publiczne uchwyty są gotowe, ale wykonawcze adaptery samplerów pozostają
poza zakresem tej wersji.

## Minimalny przykład integracyjny

Pełny przykład przepływu przez zarządzany sampler:

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(
    owner="szymo",
    mode="managed",
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
    verbose=False,
)

sampler = PiastQSampler(client.backend)
sampler.options.cft_job_name = "Bell smoke test"

job = sampler.run(circuits=[circuit], shots=200)
result = job.result()
counts = job.counts(num_bits=2)
```

Ten przykład pokazuje obecny stabilny rdzeń: Qiskitowy obwód jest serializowany
do QPY, opisany metadanymi i wysłany do dashboardu przez `PiastQSampler`.

## Filozofia projektu

`cft-piastq` trzyma granice odpowiedzialności jasno:

- Qiskit pozostaje źródłem obwodów i wyników,
- dashboard odpowiada za zarządzane wykonanie i historię zadań,
- lokalny tryb direct odpowiada za ścieżkę PCSS/AQT,
- biblioteka scala te ścieżki w jeden, jawnie konfigurowalny interfejs.

To pozwala rozwijać kolejne elementy, takie jak direct PCSS, retry, lokalny
rejestr i obsługa fake backendu, bez zmiany podstawowego kontraktu użytkownika.
