graph TD
    %% External Integrations
    subgraph "External Integrations"
        GAuth[Google Workspace OAuth<br/>AuthN: Internal Only]
        SMTP[SMTP Server<br/>Email Confirmations]
        Razorpay[Razorpay API<br/>UPI Webhooks]
        ShareAPI[Native Web Share API<br/>Client-side OTP Sharing]
    end

    %% Client / Frontend Tier
    subgraph "Frontend Tier (Jinja2 / Tailwind / Vanilla JS)"
        PubUI[Public Resident Portal<br/>Mobile Responsive]
        AdminUI[Super Admin Dashboard<br/>Desktop Focused]
        SecUI[Mobile Security Audit UI<br/>Scanner/Guard Optimized]
    end

    %% Infrastructure & Backend
    subgraph "Infrastructure Container (Docker / Portainer)"
        subgraph "Flask Backend (Python)"
            Router[Flask Routing Engine]
            RBAC[RBAC Authorization Module]
            FFlag[Global Feature Flags<br/>@require_feature_flag]
            DBPatch[SQLite Auto-Patcher<br/>Boot Schema Updates]
            
            %% Internal routing
            Router --> RBAC
            Router --> FFlag
        end

        subgraph "Data Tier (SQLite)"
            DB[(SQLite Database)]
            
            %% Tables
            Users[Users & Roles]
            Settings[Site Settings & Flags]
            Tickets[Service Tickets]
            Visitors[Visitor Logs]
            Vehicles[Vehicle & FASTag Registry]
            Amenities[Amenities & Bookings]
            
            DB --- Users
            DB --- Settings
            DB --- Tickets
            DB --- Visitors
            DB --- Vehicles
            DB --- Amenities
        end
    end

    %% Data Flow Connections
    PubUI -->|HTTP Requests| Router
    AdminUI -->|Manage Data| RBAC
    SecUI -->|Validate FASTag/OTP| RBAC

    GAuth -->|Email Handshake| Router
    Router -->|Check Role| Users
    FFlag -->|Check Boolean| Settings
    DBPatch -->|Migrate| DB
    Router -->|Read/Write| DB

    Router -->|Fire & Forget| SMTP
    Razorpay -->|POST Webhook| Router
    PubUI -->|Trigger Share Sheet| ShareAPI

    %% Styling
    classDef external fill:#f9f2f4,stroke:#333,stroke-width:1px;
    classDef frontend fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    classDef backend fill:#e8f5e9,stroke:#4caf50,stroke-width:2px;
    classDef db fill:#fff3e0,stroke:#ff9800,stroke-width:2px;

    class GAuth,SMTP,Razorpay,ShareAPI external;
    class PubUI,AdminUI,SecUI frontend;
    class Router,RBAC,FFlag,DBPatch backend;
    class DB,Users,Settings,Tickets,Visitors,Vehicles,Amenities db;
