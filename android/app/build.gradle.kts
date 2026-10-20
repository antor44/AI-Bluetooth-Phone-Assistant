plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.aiphone.switchboard"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.aiphone.switchboard"   // change to your own id before publishing
        minSdk = 24                                  // tor-android requires API 24+
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
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
    kotlinOptions {
        jvmTarget = "17"
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

    // Periodic background poll for notifications (every ~15 min)
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // Embedded Tor (Guardian Project) + its control library
    implementation("info.guardianproject:tor-android:0.4.8.17.2")
    implementation("info.guardianproject:jtorctl:0.4.5.7")
}
