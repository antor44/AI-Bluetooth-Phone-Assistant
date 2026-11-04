import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.aiphone.switchboard"
    compileSdk {
        version = release(37) {
            minorApiLevel = 2
        }
    }

    defaultConfig {
        applicationId = "com.aiphone.switchboard"   // change to your own id before publishing
        minSdk = 24                                  // tor-android requires API 24+
        targetSdk = 36
        versionCode = 6
        versionName = "1.1.4"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.webkit:webkit:1.12.1")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")

    // Material Components: modern buttons, switches, cards and time picker
    implementation("com.google.android.material:material:1.12.0")

    // Periodic background poll for notifications (power-saving mode, ~every 15 min)
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // Embedded Tor (Guardian Project) + its control library.
    // The Tor network only accepts Tor 0.4.9 or newer: do not go back to a 0.4.8.x build.
    // Versions 0.4.9.8 and newer of this library require compileSdk 37 (0.4.9.14 needs 37.1 or later).
    implementation("info.guardianproject:tor-android:0.4.9.14")
    implementation("info.guardianproject:jtorctl:0.4.5.7")
}
