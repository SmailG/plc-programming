# DEXPI (P&ID data exchange) and ISO 15926

## Versions

| Version | Date | Serialization |
|---|---|---|
| P&ID 1.3 | 2021-06-01 | Proteus Schema 4.1: `PlantInformation Application="Dexpi" ApplicationVersion="1.3" SchemaVersion="4.1"` |
| P&ID 1.4 | 2024-12-12 | Proteus 4.2.0 |
| Process 1.0 | 2023-12 | – |
| **DEXPI 2.0** | **2025-10-10** | **DEXPI XML**, which replaces Proteus and merges P&ID 1.4 with Process 1.0 (P&ID, PFD, BFD) |

The specifications are licensed CC BY 4.0: <https://gitlab.com/dexpi/Specification>.

## Proteus structure (1.x)

- The root `<PlantModel>` requires `<PlantInformation>` (with `<UnitsOfMeasure/>`).
- **Children:** `Equipment`, `PipingNetworkSystem` → `PipingNetworkSegment`,
  `ProcessInstrumentationFunction`, `InstrumentationLoopFunction`, `ActuatingSystem`,
  `ProcessSignalGeneratingSystem`, `PlantStructureItem`, `Drawing`.
- **Class mapping** uses `ComponentClass` and `ComponentClassURI` (RDL), for example
  `<Equipment ID="pump1" ComponentClass="Pump" ComponentClassURI="http://data.posccaesar.org/rdl/RDS327239">`.
- **Attributes** go in `<GenericAttributes Set="DexpiAttributes">`, and custom ones in
  `Set="CustomAttributes"`.
- **Instrumentation (1.3):**
  - A `ProcessInstrumentationFunction` carries its category letter, its functions
    letters, a modifier, a number, and fields such as `SafetyRelevanceClass`.
  - It composes a `ProcessSignalGeneratingFunction` (the sensor, e.g. "TT4750.03"), an
    `ActuatingFunction` (e.g. "HV4750.01"), an `ActuatingElectricalFunction`, a
    `SignalConveyingFunction` and a `SignalOffPageConnector`.
  - An `InstrumentationLoopFunction` groups related functions (e.g. "4750.01").
  - Signal lines are serialized as `<InformationFlow>` with `Source` and `Target`.

## DEXPI 2.0

- The root is `<Model name uri>` with `<Import source prefix>`.
- It holds both type definitions (`Package`, `ConcreteClass`, `Enumeration`, …) and
  instances: `<Object id type name>` with `<Components>`, `<References property objects>`
  and `<Data property>`.
- It is a **generic** object model, so there are no per-class tags. No real 2.0 instance
  file was inspected, so read the schema before generating one.

## From P&ID to PLC: a method, not a standard

This is an inference from the model, not a published mapping. State it as such when you
use it.

1. Take one `ProcessInstrumentationFunction` per tag. Its category and functions letters
   give the ISA-5.1 style identity, for example T + IC = TIC.
2. The `ProcessSignalGeneratingFunction` children become **inputs** (AI/DI).
   `ActuatingFunction` children become **outputs** (AO/DO).
3. Each `InstrumentationLoopFunction` becomes a **control module**: an FB instance in the
   ISA-88 sense (see the `packml-isa88-opcua` skill).
4. **Signal type, range, engineering units and fail-safe position are usually not in the
   P&ID model.** Ask for the instrument data sheets rather than inventing them.

NAMUR NE 159 (2025-06-23 edition) standardises the process-design ↔ PCT-hardware-planning
interface. Its alignment with DEXPI is unverified.

## ISO 15926 (context)

| Part | Content |
|---|---|
| 2 | Generic conceptual data model (2003) |
| 4 | Reference data library (TS 2019) |
| 7 / 8 | Templates / RDF–OWL implementation (TS 2011) |
| 11 / 12 | Simplified RDFS / life-cycle ontology in OWL |
| 14 | Industrial top-level ontology (moving to ISO 23726-3) |

DEXPI 1.3 states that it is based on ISO 15926. Its RDL URIs point to POSC Caesar
(`data.posccaesar.org/rdl/…`).
