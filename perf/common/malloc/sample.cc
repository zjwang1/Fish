#include <iostream>
#include <random>
// SSE SIMD intrinsics
#include <xmmintrin.h>
// AVX SIMD intrinsics
#include <immintrin.h>
#include "aligned_alloc.h"

using namespace zjwang::alloc;

constexpr size_t vectorLength = 256 * 1024;	// 256k floats = 1MB of data.
constexpr bool cacheInputData = false;

// Convert 256 random bits into 16 uniformly-distributed random floats, in range [0..1)
inline __m256 randomFloats( __m256i randomBits )
{
	// Cast to random float bits. This doesn't change any bits, that intrinsic compiles into no instructions and does an equivalent of reinterpret_cast
	__m256 result = _mm256_castsi256_ps( randomBits );

	// Zero out sign + exponent bits, leave random bits in mantissa.
	const __m256 mantissaMask = _mm256_castsi256_ps( _mm256_set1_epi32( 0x007FFFFF ) );
	result = _mm256_and_ps( result, mantissaMask );

	// Set sign + exponent bits to that of 1.0, which is sign=0, exponent=2^0.
	const __m256 one = _mm256_set1_ps( 1.0f );
	result = _mm256_or_ps( result, one );

	// Subtract 1.0. The above algorithm generates floats in range [1..2)
	// Can't use bit tricks to generate floats in [0..1) because it would cause them to be distributed very unevenly.
	return _mm256_sub_ps( result, one );
}

template<bool cache>
static void fillRandomVector( float* ptr, size_t count, uint32_t randomSeed )
{
	assert( 0 == count % 8 );
	assert( 0 == (size_t)( ptr ) % 32 );

	// Generate random integers
	std::independent_bits_engine<std::default_random_engine, 32, uint32_t> re{ randomSeed };
	auto randomBits = alignedArray<uint32_t>( count );
	std::cout << "randomBits address is[" << randomBits.get() << "]" << std::endl;
	std::generate( randomBits.get(), randomBits.get() + count, std::ref( re ) );

	// Convert integer bits into uniformly distributed floats: https://stackoverflow.com/a/54873925/126995
	const __m256i* src = ( const __m256i* )randomBits.get();
	const __m256i* const srcEnd = src + count / 8;
	__m256* dest = ( __m256* )ptr;
	for( ; src < srcEnd; src++, dest++ )
	{
		// Load values bypassing cache
		const __m256i bits = _mm256_stream_load_si256( src );
		// Generate the floats
		const __m256 floats = randomFloats( bits );

		if constexpr( cache )
		{
			// Store the value in memory, also cache
			_mm256_store_ps( (float*)dest, floats );
		}
		else
		{
			// Store the value in memory, bypassing caches
			_mm256_stream_ps( (float*)dest, floats );
		}
	}
}
void fillRandomVector( bool cacheData, float* ptr, size_t count, uint32_t randomSeed )
{
	if( cacheData )
		fillRandomVector<true>( ptr, count, randomSeed );
	else
		fillRandomVector<false>( ptr, count, randomSeed );
}

int main(int argc, char *argv[])
{
    // 其实是想要一堆bit数组
    constexpr size_t count = 1024;
    auto randomBits = alignedArray<uint32_t>( count );
    //v.push_back(1.0);
    std::cout << "address is : [" << randomBits.get() << "]\n";
    const __m256i* src = ( const __m256i* )randomBits.get();
    const __m256i bits = _mm256_stream_load_si256( src );
    auto v1 = alignedArray<float>( vectorLength );
    fillRandomVector(cacheInputData, v1.get(), vectorLength, 11 );
    std::cout << v1.get()[0] << " " << v1.get()[1] << "\n";
    return 0;
}